"""24-hour plan of thermostat setpoints: dynamic programming over (room temperature × heat stored). Pure Python.

Ported from the author's Node-RED "Warmte-planner" v2.8. Per quarter of an hour:
- the thermostat heats on the room error only (it does not know the floor): the learned response of the unit
  (heatpump.HeatPumpModel.demand: part of the loss plus a gain per degree below the setpoint), at most the maximum
  output, none while making hot water. The output follows the demand with the learned delay when the simulation knows
  the output at the start (the shown plan, the self-check); the search itself takes the demand at once (fast);
- the heat goes into the storage (floor, water) first and reaches the room with the learned lag — this is why floor
  heating overshoots, and why heat can be stored ahead of an expensive evening;
- electricity = heat / COP(outdoor, output); own solar (kW available that hour) is paid at its own value, the rest at
  the grid value of the hour.
Cost of an hour = electricity cost + comfort penalties (hard below the minimum, soft below the comfort temperature in
the day, mild above `warm_from`) + a cost per setpoint change; the value of the heat left after 24 hours counts too
(a deficit fully, a surplus partly: it leaks away). The setpoint is never more than `max_above_room` above the room,
so an OpenTherm thermostat keeps asking for lukewarm water (high COP).
Only the first hour is carried out; the plan is made again every quarter of an hour.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from .heatpump import HeatPumpModel
from .model import HouseModel
from .reasons import Reason
from .rooms import penalty as room_penalty
from . import savings


@dataclass
class HourIn:
    t_out: float
    wind: float
    rad: float                 # kW/m², global radiation
    p_grid: float              # currency per kWh from the grid (or battery) this hour
    p_own: float               # currency per kWh of own solar this hour (its export value)
    own_kw: float = 0.0        # own solar available for the heat pump this hour (kW)
    day: bool = True           # comfort hours
    hour: int = -1             # local hour (internal gains per hour of the day; -1: not known)
    dhw: float = 0.0           # share of the hour the unit makes hot water (no space heating then)
    extra_kw: float = 0.0      # correction from the last hours: heat the model missed (+) or had too much (−)
    away: bool = False         # nobody home: only the away minimum counts, no comfort hours
    p_imp: float | None = None  # the import price itself (price sensor, formula or contract), for showing; None: not known
    comfort_mask: tuple[bool, bool, bool, bool] | None = None  # local quarter-hours; None preserves legacy hours


@dataclass
class Settings:
    comfort: float = 20.5          # wanted in the day hours (soft)
    day_min: float = 20.0          # never below in the day hours (hard)
    night_min: float = 19.0        # never below at night (hard)
    away_min: float = 16.0         # never below while away (hard); no comfort hours then
    store_max: float = 22.5        # how warm the house may get while storing heat
    warm_from: float = 23.0        # mild penalty above this
    max_above_room: float = 1.0    # setpoint at most this above the room (lukewarm water)
    sp_min: float = 18.0
    step: float = 0.5
    penalty_hard: float = 5.0      # currency per °C·hour below the minimum
    penalty_soft: float = 0.20     # per °C·hour below the comfort temperature (day); 0.20 + switch 0.15: calm and comfortable (simulations)
    penalty_warm: float = 0.03     # per °C·hour above warm_from
    penalty_above: float = 0.0     # per °C·hour above comfort + above_margin: storing heat only when it pays
    above_margin: float = 0.3
    end_cop: str = "last"          # value of the heat left at the end: COP of the last hour ("last") or of the horizon ("mean")
    switch_cost: float = 0.05      # per setpoint change (0.15 was tuned while polish counted the end the wrong way round)
    end_factor: float = 0.6        # share of surplus heat after 24 h that still counts
    baseline_night: float | None = None   # baseline thermostat at night (None: same as the day)

    def setpoints(self) -> list[float]:
        out, sp = [], self.sp_min
        while sp <= self.store_max + 1e-9:
            out.append(round(sp, 1))
            sp += self.step
        return out


@dataclass
class HourPlan:
    sp: float
    t_end: float
    kwh: float
    heat: float
    cost: float
    price: float

    def as_dict(self) -> dict:
        return {"sp": self.sp, "t": round(self.t_end, 1), "kwh": round(self.kwh, 2), "heat": round(self.heat, 2),
                "cost": round(self.cost, 3), "price": round(self.price, 4)}


@dataclass
class Plan:
    hours: list[HourPlan]
    cost: float
    kwh: float
    baseline_cost: float
    baseline_kwh: float
    saving: float                  # raw model delta; the accepted public estimate is breakdown["saving"]
    min_day: float | None
    notes: list[str] = field(default_factory=list)
    rooms: list[list[float]] = field(default_factory=list)    # extra rooms: expected temperature at the end of each hour
    breakdown: dict = field(default_factory=dict)             # the saving per hour against the steady thermostat

    @property
    def first(self) -> HourPlan | None:
        return self.hours[0] if self.hours else None


class Simulator:
    def __init__(self, house: HouseModel, hp: HeatPumpModel, s: Settings) -> None:
        self.m, self.hp, self.s = house, hp, s
        lag = max(0.0, house.lag)
        self.rel = 1.0 if lag < 1e-6 else 1 - (1 - 1 / (1 + lag)) ** 0.25
        follow = min(1.0, max(0.01, hp.follow))
        self.aq = 1 - (1 - follow) ** 0.25          # the unit's delay per quarter of an hour
        self.stops = getattr(hp, "stops", True)     # no demand at all: the unit stops at once
        self.w_end = 0.0
        self.comfort_deficit = 0.0
        # the thermostat's demand (heatpump.HeatPumpModel.demand), unpacked: this runs millions of times per plan
        self.da, self.dk = hp.a, (hp.k if hp.k is not None else house.C)
        self.d0 = self.dk * (hp.offset - hp.th_diff)

    def hour(self, T: float, E: float, sp: float, h: HourIn, w0: float | None = None):
        """-> (T_end, E_end, cost, kWh electricity, kWh heat, comfort penalty). With w0 (output at the start, kW) the
        output follows the demand with the unit's delay, and self.w_end holds the output at the end."""
        m, s, hp = self.m, self.s, self.hp
        He = m.loss(h.wind)
        pmax = hp.pmax(h.t_out)
        share = 1.0 - min(1.0, max(0.0, h.dhw))         # hot water first: no space heating meanwhile
        sun = m.g * h.rad
        cost = kwh = heat = pen = 0.0
        own = h.own_kw * 0.25
        hard = s.away_min if h.away else (s.day_min if h.day else s.night_min)
        lagged = w0 is not None and self.aq < 1.0
        w = w0 or 0.0
        internal = m.internal_at(h.hour)
        self.comfort_deficit = 0.0
        for quarter in range(4):
            day = h.comfort_mask[quarter] if h.comfort_mask is not None else h.day
            hard = s.away_min if h.away else (s.day_min if day else s.night_min)
            loss = He * (T - h.t_out) - internal - h.extra_kw
            d = self.da * (loss - sun) + self.dk * (sp - T) + self.d0
            if d <= 0 and self.stops:
                w = d = 0.0
            else:
                d = (0.0 if d < 0 else (pmax if d > pmax else d)) * share
                w = w + self.aq * (d - w) if lagged else d
            E += w * 0.25
            r = E * self.rel
            E -= r
            T += (r + (sun - loss) * 0.25) / m.C
            if w > 0:
                cop = hp.cop(h.t_out, w)
                if w < hp.q_min:
                    cop *= hp.cyc                 # below its lowest output the unit cycles on and off
                e = w * 0.25 / cop
                eo = e if e < own else own
                cost += eo * h.p_own + (e - eo) * h.p_grid
                kwh += e
                heat += w * 0.25
            if T < hard:
                pen += (hard - T) * 0.25 * s.penalty_hard
            if day and not h.away and T < s.comfort:
                self.comfort_deficit += (s.comfort - T) * 0.25
                pen += (s.comfort - T) * 0.25 * s.penalty_soft
            if T > s.warm_from:
                pen += (T - s.warm_from) * 0.25 * s.penalty_warm
            if s.penalty_above and T > s.comfort + s.above_margin:
                pen += (T - s.comfort - s.above_margin) * 0.25 * s.penalty_above
        self.w_end = w
        return T, E, cost, kwh, heat, pen


def baseline_sp(s: Settings, hp: HeatPumpModel, house: HouseModel, h: HourIn) -> float:
    """The steady thermostat to compare with: the setpoint that holds the room (not the thermostat's own reading) at
    the comfort temperature (or the night setting) in this hour's weather, from the unit's learned response."""
    room = s.away_min if h.away else (s.comfort if (h.day or s.baseline_night is None) else s.baseline_night)
    k = hp.k if hp.k is not None else house.C
    loss = house.loss(h.wind) * (room - h.t_out) - house.g * h.rad - house.internal_at(h.hour)
    return room + hp.th_diff - hp.offset + (1 - hp.a) * max(0.0, loss) / max(0.1, k)


def _deficit(T: float, h: HourIn, s: Settings, quarter_deficit: float = 0.0) -> float:
    """Comfort shortfall at the end of an hour (°C), counted in the comfort hours only."""
    if h.comfort_mask is not None:
        return quarter_deficit
    return max(0.0, s.comfort - T) if h.day and not h.away else 0.0


def comparable_steady(sim: Simulator, hours: list[HourIn], T0: float, E0: float, w0: float | None, house: HouseModel,
                      deficit: float, trace: dict | None = None) -> tuple[float, float, float, float]:
    """The steady thermostat to compare with, at equal comfort: one offset on the setpoint that holds the comfort
    temperature, the lowest that is at least as comfortable as the plan (°C·hours below comfort in the comfort hours).
    Comparing with a colder steady thermostat would make a comfortable plan look expensive. -> (cost, kWh, T, E).
    On the same steps as the plan, as a real thermostat; when one step is a little too cold and the next too warm, the
    two are weighed to exactly the plan's comfort — taking the warmer step whole made a plan look like it saved what
    the step costs (#5), the colder one like it cost it.
    `trace`: filled with what the chosen steady thermostat does per hour (setpoint, room, kWh, cost), for the breakdown."""
    s, hp = sim.s, sim.hp
    last = prev = None
    for off in [x / 10 for x in range(-5, 16)]:
        T, E, w, cost, kwh, dfc = T0, E0, w0, 0.0, 0.0, 0.0
        rows = []
        for h in hours:
            sp = round((baseline_sp(s, hp, house, h) + off) / s.step) * s.step     # a thermostat has steps too
            T, E, c, e, _q, _ = sim.hour(T, E, sp, h, w)
            w = sim.w_end if w is not None else None
            cost, kwh, dfc = cost + c, kwh + e, dfc + _deficit(T, h, s, sim.comfort_deficit)
            rows.append((sp, T, e, c))
        if last is not None and rows != last[5]:
            prev = last
        last = (cost, kwh, T, E, dfc, rows, off)
        if dfc <= deficit + 0.05:
            break
    cost, kwh, T, E, dfc, rows, off = last
    if prev is not None and dfc < deficit < prev[4]:
        wt = (prev[4] - deficit) / (prev[4] - dfc)        # share of the warmer step
        mix = lambda a, b: a * (1 - wt) + b * wt           # noqa: E731
        cost, kwh, T, E, off = (mix(prev[i], x) for i, x in ((0, cost), (1, kwh), (2, T), (3, E), (6, off)))
        rows = [tuple(mix(a, b) for a, b in zip(ra, rb)) for ra, rb in zip(prev[5], rows)]
        dfc = deficit
    if trace is not None:           # per hour (setpoint, room at the end, kWh, cost), the offset and its comfort shortfall
        trace.update(rows=rows, offset=off, deficit=dfc)
    return cost, kwh, T, E


def _end_value(sim: Simulator, hours: list[HourIn], comfort: float):
    """-> f(T, E): what the state at the end still costs, to compare plans that end differently: the heat short of
    comfort bought back later (positive), heat above comfort partly counted as already bought (negative). Still away
    at the end: the away minimum is what the house needs then, not the comfort temperature."""
    if hours and hours[-1].away:
        comfort = sim.s.away_min
    elif hours and hours[-1].comfort_mask is not None and not hours[-1].comfort_mask[-1]:
        comfort = sim.s.night_min
    tail = hours[-6:] or hours
    price = sum(h.p_grid for h in tail) / len(tail)
    cop = sim.hp.cop(hours[-1].t_out, 3.5) if sim.s.end_cop == "last" else \
        sum(sim.hp.cop(h.t_out, 3.0) for h in hours) / len(hours)
    C = sim.m.C

    def value(T: float, E: float) -> float:
        d = T + E / C - comfort
        return -d * C / cop * price * (1.0 if d < 0 else sim.s.end_factor)
    return value


SLOW = 0.67             # a unit closing less of a change per hour than this is planned with its delay (polish)
HOLD_MARGIN = 0.25       # a setpoint already set may stay this much further above the room than max_above_room
BLOCKS = (1, 2, 4)      # polish: try a setpoint for this many hours at once. Longer blocks and more starting plans
                        # found cheaper plans on the model but not in closed-loop simulations (tools/sim): they exploit model errors


def start_output(sim: Simulator, T: float, sp: float, h: HourIn) -> float:
    """The unit's output now when it is not measured: what it settles at for this setpoint."""
    sim.hour(T, 0.0, sp, h)
    return sim.w_end


def room_temps(sim: Simulator, hours: list[HourIn], t_now: float, e_now: float, w_now: float | None, seq: list[float],
               rooms: list[dict]) -> list[list[float]]:
    """Expected temperature of each extra room at the end of each hour of a plan."""
    T, E, w = t_now, e_now, w_now
    trs = [r["T"] for r in rooms]
    out: list[list[float]] = [[] for _ in rooms]
    for k, sp in enumerate(seq):
        T1, E, _c, _e, q, _p = sim.hour(T, E, sp, hours[k], w)
        w = sim.w_end if w is not None else None
        for i, r in enumerate(rooms):
            trs[i] = r["model"].step(trs[i], q, hours[k].t_out, (T + T1) / 2)
            out[i].append(round(trs[i], 2))
        T = T1
    return out


def polish(sim: Simulator, hours: list[HourIn], t_now: float, e_now: float, w_now: float, sp_now: float | None,
           starts: list[list[float]], sps: list[float], end, t_lo: float, rooms: list[dict] | None = None) -> list[float]:
    """Improve a plan of setpoints with the unit's real delay: from the best start, set blocks of 1, 2 and 4 hours to
    another setpoint and keep what lowers cost + comfort penalties (also of the extra rooms) + changes − the value of
    the heat left at the end."""
    s, hp = sim.s, sim.hp
    H = len(hours)
    rooms = rooms or []

    def run(seq: list[float], k0: int = 0, state=None):
        """-> total, states (T, E, w, running total, previous setpoint, extra room temperatures) at the start of each hour"""
        T, E, w, tot, prev, trs = state if state else (t_now, e_now, w_now, 0.0, sp_now, tuple(r["T"] for r in rooms))
        states = []
        for k in range(k0, H):
            states.append((T, E, w, tot, prev, trs))
            sp = seq[k]
            # not allowed: too far above what the thermostat reads (an OpenTherm thermostat then asks for hot water,
            # 37 °C instead of 32 at 1.3 °C above). Keeping the setpoint already set may go a little further, so a room
            # a tenth cooler does not make it step down and up again.
            if sp > T + hp.th_diff + s.max_above_room + (HOLD_MARGIN if sp == prev else 0.0) + 1e-9 and sp > s.day_min and sp > sps[0]:
                tot += 10.0
            T1, E, c, _e, q, pen = sim.hour(T, E, sp, hours[k], w)
            w = sim.w_end
            if rooms:
                trs = tuple(r["model"].step(tr, q, hours[k].t_out, (T + T1) / 2) for r, tr in zip(rooms, trs))
                pen += sum(room_penalty(tr, r["min"]) for r, tr in zip(rooms, trs) if r["active"][k])
            T = T1
            tot += c + pen + (s.switch_cost if prev is not None and sp != prev else 0.0)
            prev = sp
        return tot + end(T, E), states

    best, best_states = None, None
    for st in starts:
        st = list(st[:H]) + [st[-1]] * (H - len(st))
        v, states = run(st)
        if best is None or v < best[0]:
            best, best_states = (v, st), states
    val, seq = best
    states = best_states
    for _ in range(3):
        improved = False
        for k in range(H):
            for L in BLOCKS:
                if k + L > H:
                    continue
                for v in sps:
                    if all(x == v for x in seq[k:k + L]):
                        continue
                    cand = seq[:k] + [v] * L + seq[k + L:]
                    tot, _ = run(cand, k, states[k])
                    if tot < val - 1e-6:
                        val, seq = tot, cand
                        _, tail = run(seq, k, states[k])
                        states = states[:k] + tail
                        improved = True
        if not improved:
            break
    return seq


def plan(house: HouseModel, hp: HeatPumpModel, s: Settings, hours: list[HourIn], t_now: float, e_now: float,
         sp_now: float | None, report: int = 24, w_now: float | None = None, rooms: list[dict] | None = None,
         fixed: list[float] | None = None, extra_rooms: int | None = None) -> Plan:
    """Plan over all `hours` (give ~36 so the last shown hours are not distorted by the horizon), report the first
    `report` hours (plan, cost, kWh, saving with the state after `report` hours levelled). w_now: the unit's heat
    output now (kW); the reported hours then follow the unit's delay. fixed: keep these setpoints (a plan held,
    stick.py) and only work out what they give now. extra_rooms: the rooms configured (some may be unread now)."""
    sim = Simulator(house, hp, s)
    if fixed:
        return _report(sim, house, hp, s, hours, t_now, e_now, report, w_now, rooms, list(fixed[:len(hours)]) +
                       [fixed[-1]] * max(0, len(hours) - len(fixed)), extra_rooms)
    sps = s.setpoints()
    NA = len(sps)
    t_lo = min(s.night_min, t_now) - 3.0
    t_hi = max(s.store_max, t_now) + 2.0
    dT = 0.1
    NT = int(round((t_hi - t_lo) / dT)) + 1
    use_e = house.lag >= 0.3
    e_max, dE = 20.0, 1.0
    NE = int(e_max / dE) + 1 if use_e else 1
    end = _end_value(sim, hours, s.comfort)
    H = len(hours)
    end_r = _end_value(sim, hours[:min(report, H)], s.comfort)

    # V[i][j][a]: cost-to-go from room index i, storage index j, with setpoint a currently on the thermostat
    V = [[[end(t_lo + i * dT, j * dE)] * NA for j in range(NE)] for i in range(NT)]

    def interp(Vv, T: float, E: float, a: int) -> float:
        x = (T - t_lo) / dT
        x = 0.0 if x < 0 else (NT - 1.000001 if x > NT - 1.000001 else x)
        i0 = int(x)
        fx = x - i0
        if NE == 1:
            return Vv[i0][0][a] * (1 - fx) + Vv[i0 + 1][0][a] * fx
        y = E / dE
        y = 0.0 if y < 0 else (NE - 1.000001 if y > NE - 1.000001 else y)
        j0 = int(y)
        fy = y - j0
        r0 = Vv[i0][j0][a] * (1 - fx) + Vv[i0 + 1][j0][a] * fx
        r1 = Vv[i0][j0 + 1][a] * (1 - fx) + Vv[i0 + 1][j0 + 1][a] * fx
        return r0 * (1 - fy) + r1 * fy

    choice: list = [None] * H
    for k in range(H - 1, -1, -1):
        h = hours[k]
        Vn = [[[0.0] * NA for _ in range(NE)] for _ in range(NT)]
        ch = [[[0] * NA for _ in range(NE)] for _ in range(NT)]
        for i in range(NT):
            T0 = t_lo + i * dT
            # at most max_above_room above what the thermostat reads (lukewarm water); the lowest setting always (it
            # may be above the day minimum: in a cold room nothing would be left)
            allowed = [a for a in range(NA) if sps[a] <= T0 + hp.th_diff + s.max_above_room or sps[a] <= s.day_min or a == 0]
            for j in range(NE):
                E0 = j * dE
                base = {}
                for a in allowed:
                    T1, E1, c, _kwh, _q, pen = sim.hour(T0, E0, sps[a], h)
                    if NE == 1:
                        T1 += E1 / house.C          # not tracked: what is still on its way reaches the room, not lost
                    base[a] = c + pen + interp(V, T1, E1, a)
                best_a = min(base, key=base.get)
                best = base[best_a] + s.switch_cost
                row_v, row_c = Vn[i][j], ch[i][j]
                for prev in range(NA):
                    stay = base.get(prev)
                    if stay is not None and stay <= best:
                        row_v[prev], row_c[prev] = stay, prev
                    else:
                        row_v[prev], row_c[prev] = best, best_a
        V, choice[k] = Vn, ch

    # the search's choices over the whole horizon, from the real state
    # not known (the thermostat unavailable just after a start): from the lowest setting, never an arbitrary middle one
    prev = min(range(NA), key=lambda a: abs(sps[a] - sp_now)) if sp_now is not None else 0
    T, E = t_now, e_now
    seq: list[float] = []
    for k in range(H):
        i = min(NT - 1, max(0, int(round((T - t_lo) / dT))))
        j = min(NE - 1, max(0, int(round(E / dE)))) if NE > 1 else 0
        prev = choice[k][i][j][prev]
        seq.append(sps[prev])
        T, E, *_ = sim.hour(T, E, sps[prev], hours[k])
        if NE == 1:
            T, E = T + E / house.C, 0.0
    if hp.follow < SLOW or rooms:
        # a unit that follows the thermostat slowly (OpenTherm, modulating): the search above takes a new setpoint as
        # working at once, so improve its plan with the real delay (and never end up worse than a steady thermostat).
        # Extra rooms (rooms.py) are only known here: their minimums are kept in the same step
        w0 = w_now if w_now is not None else start_output(sim, t_now, sp_now if sp_now is not None else seq[0], hours[0])
        steady = [round(baseline_sp(s, hp, house, h) * 2) / 2 for h in hours]
        seq = polish(sim, hours, t_now, e_now, w0, sp_now, [seq, steady], sps, end, t_lo, rooms)
        w_now = w0
    return _report(sim, house, hp, s, hours, t_now, e_now, report, w_now, rooms, seq, extra_rooms)


def _report(sim: Simulator, house: HouseModel, hp: HeatPumpModel, s: Settings, hours: list[HourIn], t_now: float,
            e_now: float, report: int, w_now: float | None, rooms: list[dict] | None, seq: list[float],
            extra_rooms: int | None) -> Plan:
    """The plan for a chosen sequence of setpoints: forward from the real state, against the steady thermostat."""
    H = len(hours)
    end_r = _end_value(sim, hours[:min(report, H)], s.comfort)
    if w_now is None and hp.follow < SLOW and hours:
        w_now = start_output(sim, t_now, seq[0], hours[0])
    # forward from the real state
    T, E = t_now, e_now
    out: list[HourPlan] = []
    total = kwh_tot = 0.0
    min_day = None
    R = min(report, H)
    w = w_now
    deficit = 0.0
    for k in range(R):
        T1, E1, c, e, q, _ = sim.hour(T, E, seq[k], hours[k], w)
        w = sim.w_end if w is not None else None
        out.append(HourPlan(seq[k], T1, e, q, c, hours[k].p_grid))
        deficit += _deficit(T1, hours[k], s, sim.comfort_deficit)
        total += c
        kwh_tot += e
        if hours[k].day:
            min_day = T1 if min_day is None else min(min_day, T1)
        T, E = T1, E1

    # the steady thermostat to compare with, at equal comfort
    trace: dict = {}
    base_cost, base_kwh, Tb, Eb = comparable_steady(sim, hours[:R], t_now, e_now, w_now, house, deficit, trace)
    saving = base_cost - total + end_r(Tb, Eb) - end_r(T, E)
    room_t = room_temps(sim, hours[:R], t_now, e_now, w_now, seq[:R], rooms) if rooms else []
    bd = breakdown(hours[:R], [(x.sp, x.t_end, x.kwh, x.cost) for x in out], trace, end_r(T, E), end_r(Tb, Eb), deficit)
    bd = savings.publish(bd, savings.comparison(deficit, trace.get("deficit", 0),
                                                extra_rooms if extra_rooms is not None else len(rooms or [])))
    return Plan(out, total, kwh_tot, base_cost, base_kwh, saving, min_day, rooms=room_t, breakdown=bd)


SUNNY = 0.1             # kW/m² global radiation: an hour with sun on the house (breakdown)


def breakdown(hours: list[HourIn], roost: list[tuple], steady: dict, end_roost: float, end_steady: float,
              deficit: float) -> dict:
    """Where a saving comes from, hour by hour: what Roost does and what the steady thermostat at equal comfort does
    (setpoint, room at the end of the hour, kWh, cost), and what the state at the end of the period still costs
    for each (_end_value). saving = Σ (steady − Roost) + end steady − end Roost."""
    rows = []
    for k, (h, r, b) in enumerate(zip(hours, roost, steady.get("rows", []))):
        rows.append({"i": k, "hour": h.hour, "t_out": round(h.t_out, 1), "price": round(h.p_grid, 4), "day": h.day,
                     # the tariff beside what the plan counts (they differ while a home battery supplies the house)
                     "tariff": None if h.p_imp is None else round(h.p_imp, 4),
                     "sun": h.rad >= SUNNY,
                     "sp": round(r[0], 1), "t": round(r[1], 2), "kwh": round(r[2], 3), "cost": round(r[3], 4),
                     "b_sp": round(b[0], 1), "b_t": round(b[1], 2), "b_kwh": round(b[2], 3), "b_cost": round(b[3], 4),
                     "save": round(b[3] - r[3], 4)})
    cost, base = sum(r[3] for r in roost), sum(b[3] for b in steady.get("rows", []))
    kwh, b_kwh = sum(r[2] for r in roost), sum(b[2] for b in steady.get("rows", []))
    # the saving in parts that add up: less electricity (at the steady thermostat's average price: waiting for the sun,
    # no overshoot, warmer hours), of which in sunny hours, cheaper hours (the rest of the cost), the state at the end
    avg = base / b_kwh if b_kwh > 0.01 else (sum(h.p_grid for h in hours) / len(hours) if hours else 0.0)
    less = (b_kwh - kwh) * avg
    sun = sum((b[2] - r[2]) * avg for h, r, b in zip(hours, roost, steady.get("rows", [])) if h.rad >= SUNNY)
    parts = {"less_kwh": round(less, 3), "sun": round(sun, 3), "cheaper_hours": round(base - cost - less, 3),
             "end": round(end_steady - end_roost, 3)}
    return {"hours": rows, "cost": round(cost, 3), "b_cost": round(base, 3), "parts": parts,
            "kwh": round(kwh, 2), "b_kwh": round(b_kwh, 2),
            "end": round(end_roost, 3), "b_end": round(end_steady, 3),
            "saving": round(base + end_steady - cost - end_roost, 3),
            "short": round(deficit, 2), "b_short": round(steady.get("deficit", 0.0), 2),
            "b_offset": round(steady.get("offset", 0.0), 1)}


PRICE_SPREAD = 0.05     # prices within 5 % of each other are one price: no hour is cheap or dear then


def neutral_prices(hours: list[HourIn], guess: list[bool], window: int = 24) -> list[HourIn] | None:
    """The hours with every guessed price (past the published ones, filled from a day earlier) set to the mean of
    the published ones: a plan that only differs from the normal one through guessed prices must not change the
    thermostat. None when no hour in the first `window` is a guess."""
    if not any(guess[:window]):
        return None
    known = [h.p_grid for i, (h, g) in enumerate(zip(hours, guess + [True] * len(hours))) if i == 0 or not g]
    if not known:
        return None
    mean = sum(known) / len(known)
    out = []
    for i, h in enumerate(hours):
        if i == 0 or (i < len(guess) and not guess[i]):      # the current hour's price is always known
            out.append(h)
        else:
            own = mean if abs(h.p_own - h.p_grid) < 1e-9 else min(h.p_own, mean)
            out.append(replace(h, p_grid=mean, p_own=own))
    if all(abs(a.p_grid - b.p_grid) < 1e-9 and abs(a.p_own - b.p_own) < 1e-9 for a, b in zip(hours, out)):
        return None                     # the guesses already are the mean (a price without forecast): nothing to plan again
    return out


def explain(p: Plan, hours: list[HourIn], room: float, s: Settings, hp: HeatPumpModel | None = None,
            house: HouseModel | None = None, floor: bool = True, i: int = 0) -> Reason:
    """One line on why hour i (0: now) is what it is: the setpoint against the one that would just hold the comfort
    temperature (the thermostat may read differently from the room sensor, and the unit may heat towards another
    temperature than the setpoint). room: the room at the start of hour i. Cheap and dear are judged on the price the
    planner counts (own solar, the battery's refill cost or the tariff) against the twelve hours around it."""
    if len(p.hours) <= i or len(hours) <= i:
        return Reason("no_plan")
    ph, h = p.hours[i], hours[i]
    sp = ph.sp
    hold = baseline_sp(Settings(comfort=s.comfort), hp, house, h) if hp and house else s.comfort
    th = hp.th_diff if hp else 0.0
    j = max(0, min(i, len(p.hours) - 12))
    prices = sorted(x.price for x in p.hours[j:j + 12])
    now = ph.price
    # cheap or dear only where prices really differ: with one fixed rate every hour would be both (#4)
    spread = (prices[-1] - prices[0]) / max(0.01, sum(prices) / len(prices))
    cheap = spread > PRICE_SPREAD and now <= prices[len(prices) // 3]
    dear = spread > PRICE_SPREAD and now >= prices[(2 * len(prices)) // 3]
    if ph.heat < 0.1 and sp <= room + th:
        # no heat this hour: the room is warmer than the setpoint (sun, a warm day), whatever the price — not storing
        return Reason("warm_enough", {"room": round(room, 1)})
    if h.own_kw >= 0.5 and sp > hold + 0.25:
        return Reason("store_solar" if floor else "store_solar_house", {"sp": sp})
    if sp > hold + 0.25 and cheap:
        return Reason("store_cheap" if floor else "store_cheap_house", {"ct": round(now * 100, 1)})
    if sp > hold + 0.25:
        # warmer than holding, but not a cheap hour: heat ahead of dearer hours to come (a slow floor needs the start)
        for k in range(i + 1, min(len(p.hours), len(hours), i + 13)):
            if p.hours[k].price >= now * (1 + PRICE_SPREAD) + 0.005:
                return Reason("store_ahead" if floor else "store_ahead_house",
                              {"ct": round(p.hours[k].price * 100, 1), "at": hours[k].hour if hours[k].hour >= 0 else k - i})
    if sp < hold - 0.25 and dear:
        return Reason("expensive" if floor else "expensive_house", {"ct": round(now * 100, 1)})
    if sp <= room + th - 0.5:
        return Reason("warm_enough", {"room": round(room, 1)})
    return Reason("holding", {"sp": sp})


def explain_hours(p: Plan, hours: list[HourIn], room: float, s: Settings, hp: HeatPumpModel | None = None,
                  house: HouseModel | None = None, floor: bool = True) -> list[Reason]:
    """Why each hour of the plan is what it is, each from the room the plan expects at its start."""
    rooms = [room] + [x.t_end for x in p.hours[:-1]]
    return [explain(p, hours, rooms[i], s, hp, house, floor, i) for i in range(min(len(p.hours), len(hours)))]


REPLAY_VERSION = 5      # v0.8.0: the unit stops at once without demand; v0.7.8: quarter-hour weekly comfort


def replay_day(house: HouseModel, hp: HeatPumpModel, s: Settings, entries: list[dict]) -> tuple[float, float, dict] | None:
    """Yesterday twice with the same model, weather and prices, from the same start: once with the setpoints Roost
    set (or would have set, in shadow mode), once with a steady thermostat. -> (cost with Roost, cost steady, breakdown),
    each with what the state at the end still costs added the same way."""
    if not entries:
        return None
    hours = [HourIn(t_out=e["t_out"], wind=e.get("wind", 3.5), rad=e.get("rad", 0.0), p_grid=e["p_grid"], p_own=e.get("p_own", e["p_grid"]),
                    own_kw=e.get("own", 0.0), day=e.get("day", True), dhw=e.get("dhw", 0.0), hour=e.get("hour", -1), comfort_mask=e.get("comfort_mask"),
                    away=e.get("away", False), p_imp=e.get("p_imp")) for e in entries]
    sim = Simulator(house, hp, s)
    end = _end_value(sim, hours, s.comfort)
    T0, E0 = entries[0]["T"], entries[0].get("E", 0.0)
    # The same output at the start for both alternatives, with the same learned delay as the forward plan.
    sp0 = float(entries[0].get("sp_mean", entries[0]["sp"]))
    w0 = entries[0].get("w")
    if w0 is None:
        w0 = start_output(sim, T0, sp0, hours[0])
    w = w0
    T, E, cost, deficit = T0, E0, 0.0, 0.0
    rows = []
    for e, h in zip(entries, hours):
        sp = float(e.get("sp_mean", e["sp"]))
        T, E, c, kwh, *_ = sim.hour(T, E, sp, h, w)
        w = sim.w_end
        cost += c
        deficit += _deficit(T, h, s, sim.comfort_deficit)
        rows.append((sp, T, kwh, c))
    trace: dict = {}
    base, _kwh, Tb, Eb = comparable_steady(sim, hours, T0, E0, w0, house, deficit, trace)
    bd = breakdown(hours, rows, trace, end(T, E), end(Tb, Eb), deficit)
    for r, e in zip(bd["hours"], entries):
        r["ts"] = e.get("ts")
    return cost + end(T, E), base + end(Tb, Eb), bd
