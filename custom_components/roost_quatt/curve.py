"""Heating curve advice: the flow temperature the house needs at each outdoor temperature. Pure Python.

For a heat pump that runs on its own heating curve (the thermostat only switches it on and off), the curve decides how
warm the water is: too high costs efficiency, too low leaves the house cold. The advice comes from the unit's own logs:

1. What the house needs (energy signature): per whole day the mean heat for space heating against the difference
   between room and outdoor temperature, a straight line. The spread of the cold days above that line is the margin
   (mild days spread far more — sun, people, cooking — and say little about the curve where it matters).
2. What the floor or radiators give off: Q = k · (flow − room)^n (EN 442). n is fixed by the kind of emitter (floor
   1.1, radiators 1.3, both 1.2); measured n almost always comes out too low, so only k comes from the data: the hours
   the unit ran the whole hour on space heating.
3. The curve: per outdoor temperature the flow that delivers the need (with the margin) at the comfort temperature,
   as five points (outdoor -10, -5, 0, 5 and 10 °C). The line between two points is straight while the need curves, so each point
   is set just high enough that the line stays on or above the need. Every point gets a value:
   where no heat is needed any more, the room temperature. Where the need is below the unit's lowest output it
   switches on and off whatever the curve says (the cycling zone), so the points there matter little. That limit is
   measured: the outdoor temperature from which most heating hours were interrupted (else from the lowest output).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from .model import HourRow

EMITTER_N = {"floor": 1.1, "radiators": 1.3, "both": 1.2}
CURVE_X = (-10.0, -5.0, 0.0, 5.0, 10.0)       # outdoor temperatures of the five points shown
SIGNATURE_MAX_OUT = 12.0     # days warmer than this hardly heat: the line bends there (heating limit), leave them out
MIN_DAY_HEAT_KW = 0.3        # a day with less heat than this did not really heat
STEADY_S = 3300              # seconds of space heating in an hour to count as running the whole hour
MIN_EXCESS = 3.0             # flow at least this much above the room: below it the relation drowns in noise
MARGIN_Q = 0.75              # the line covers the need on three cold days out of four: measured hours in frost
                             # needed less than more margin would give, and the thermostat still switches it
MARGIN_MAX_OUT = 5.0         # the margin from days this cold or colder (when there are enough of them)
MARGIN_MIN_DAYS = 10
MIN_DAYS, MIN_HOURS = 20, 30
RELIABLE_DAYS, RELIABLE_HOURS, RELIABLE_SE = 30, 50, 0.10
NEAR = 2.0                   # °C: hours this close to a point count for what the unit made there
CLOUD_MAX = 300              # steady hours kept for the card's graph (evenly over all of them)
CYCLING_RUN_S = 3420         # an hour with less space heating than this (95 %) was interrupted
CYCLING_MIN_HOURS = 10       # hours per degree of outdoor temperature to judge it


@dataclass
class CurveAdvice:
    points: list[list]            # [outdoor °C, advised flow °C, measured flow there or None]
    room: float                   # indoor temperature the advice is for
    ua_kw: float                  # heat loss, kW per °C between room and outdoor
    base_kw: float                # intercept of the signature (minus the free heat from people, appliances, sun)
    margin_kw: float
    k_kw: float                   # emitter: kW at 1 °C flow above the room
    n: float
    cycling_from: float | None    # outdoor °C above which the need is below the lowest output
    days: int
    hours: int
    out_min: float                # coldest and warmest day in the signature
    out_max: float
    reliable: bool
    extrapolated: list[float] = field(default_factory=list)   # points colder than any day measured
    measured_by: str | None = None    # what controlled the unit in the measured hours: opentherm | heating_curve
    cloud: list[list[float]] = field(default_factory=list)    # [outdoor, flow] of the steady hours (at most CLOUD_MAX)
    cold_hour: float | None = None    # the coldest hour the unit heated in: colder than this the curve is calculated

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> CurveAdvice | None:
        if not d:
            return None
        try:
            return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        except TypeError:
            return None

    def flow_at(self, t_out: float) -> float | None:
        """The advised curve (the five points, straight between them) at an outdoor temperature."""
        pts = [(x, y) for x, y, _m in self.points if y is not None]
        if not pts:
            return None
        if t_out <= pts[0][0]:
            return pts[0][1]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if t_out <= x1:
                return y0 + (y1 - y0) * (t_out - x0) / (x1 - x0)
        return None


def signature(rows: list[HourRow]) -> tuple[float, float, float, list[tuple[float, float]]] | None:
    """Whole days (UTC) with heating: mean heat (kW) = ua · (room − outdoor) + base.
    -> (ua, base, standard error of ua, [(outdoor, residual kW)])"""
    by_day: dict[int, list[HourRow]] = {}
    for r in rows:
        by_day.setdefault(r.ts // 86400, []).append(r)
    pts = []
    for hs in by_day.values():
        if len(hs) < 24:
            continue
        q = sum(h.Q for h in hs) / 24
        t_in, t_out = sum(h.T for h in hs) / 24, sum(h.T_out for h in hs) / 24
        if q >= MIN_DAY_HEAT_KW and t_out <= SIGNATURE_MAX_OUT:
            pts.append((t_in - t_out, q, t_out))
    if len(pts) < MIN_DAYS:
        return None
    n = len(pts)
    mx, my = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    if sxx <= 0:
        return None
    ua = sum((p[0] - mx) * (p[1] - my) for p in pts) / sxx
    if ua <= 0:
        return None
    base = my - ua * mx
    res = [(p[2], p[1] - (ua * p[0] + base)) for p in pts]
    se = (sum(e * e for _t, e in res) / max(1, n - 2) / sxx) ** 0.5
    return ua, base, se, res


def _steady(r: HourRow, f: float | None) -> bool:
    return f is not None and r.heating_s >= STEADY_S and r.dhw_s <= 60 and r.Q >= 0.5 and f - r.T >= MIN_EXCESS


def steady_hours(rows: list[HourRow], flows: dict[int, float]) -> list[tuple[float, float, float, float]]:
    """Hours the unit ran the whole hour on space heating: (outdoor, room, flow, kW)."""
    return [(r.T_out, r.T, flows[r.ts], r.Q) for r in rows if _steady(r, flows.get(r.ts))]


def measured_by(rows: list[HourRow], flows: dict[int, float], opentherm: set[int]) -> str | None:
    """What controlled the unit in the steady hours: an OpenTherm thermostat asking a water temperature (the
    CIC's control setpoint per hour), else the unit's own heating curve. None when the logs do not tell (imported before)."""
    if not opentherm:
        return None
    hours = [r.ts for r in rows if _steady(r, flows.get(r.ts))]
    if not hours:
        return None
    return "opentherm" if sum(1 for t in hours if t in opentherm) * 2 > len(hours) else "heating_curve"


def cycling_limit(rows: list[HourRow]) -> float | None:
    """The outdoor temperature (°C, whole degrees) from which most hours with space heating were interrupted (the
    unit switched on and off instead of running through), and stay so in milder weather."""
    bins: dict[int, list[int]] = {}
    for r in rows:
        if r.heating_s > 600 and r.dhw_s <= 60:
            b = bins.setdefault(int(r.T_out // 1), [0, 0])
            b[0] += 1
            b[1] += r.heating_s < CYCLING_RUN_S
    known = sorted(t for t, (n, _i) in bins.items() if n >= CYCLING_MIN_HOURS)
    if len(known) < 5:
        return None
    for i, t in enumerate(known):
        if all(bins[u][1] * 2 >= bins[u][0] for u in known[i:]):
            return float(t) if i else None          # interrupted already in the coldest weather seen: not known
    return None


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def _quantile(xs: list[float], q: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, max(0, round(q * (len(s) - 1))))]


def _up(v: float) -> float:
    """Up to the next half degree: on the warm side of the need."""
    return -(-v * 2 // 1) / 2


def advise(rows: list[HourRow], flows: dict[int, float], emitter: str, room: float, q_min: float = 0.0,
           xs: tuple[float, ...] = CURVE_X, opentherm: set[int] | None = None) -> CurveAdvice | None:
    """rows: the learning history; flows: {hour ts: mean flow temperature (°C)} from the unit's hours; emitter: floor,
    radiators or both; room: the comfort temperature; q_min: the unit's lowest steady output (kW, 0: unknown)."""
    sig = signature(rows)
    steady = steady_hours(rows, flows)
    if sig is None or len(steady) < MIN_HOURS:
        return None
    ua, base, se, res = sig
    n = EMITTER_N.get(emitter, EMITTER_N["floor"])
    k = _median([q / (f - t) ** n for _o, t, f, q in steady])
    cold = [e for t, e in res if t <= MARGIN_MAX_OUT]
    margin = max(0.0, _quantile(cold if len(cold) >= MARGIN_MIN_DAYS else [e for _t, e in res], MARGIN_Q))

    def need(t_out: float) -> float:
        return ua * (room - t_out) + base

    def flow(t_out: float) -> float | None:
        q = need(t_out) + margin
        return room + (q / k) ** (1 / n) if q > 0 else None

    cycling = cycling_limit(rows)
    if cycling is None and q_min > 0:
        cycling = room - (q_min - base) / ua
    top = room + (base + margin) / ua           # above this not even the margin asks for heat
    points: list[list] = []
    prev: tuple[float, float] | None = None
    for x in xs:
        made = [f for o, _t, f, _q in steady if abs(o - x) <= NEAR]
        made_at = round(_median(made), 1) if len(made) >= 3 else None
        if prev is None:
            f0 = flow(x)
            y = _up(f0) if f0 is not None and x < top else _up(room)
        elif prev[0] >= top:
            y = _up(room)                                       # no heat needed: water at room temperature
        else:
            # the straight line from the previous point must stay on or above the need up to here (or the limit)
            x0, y0 = prev
            y = None
            end = min(x, top)
            steps = max(2, int((end - x0) * 4))
            for i in range(1, steps + 1):
                t = x0 + (end - x0) * i / steps
                f = flow(t)
                if f is None:
                    continue
                need_y = y0 + (f - y0) * (x - x0) / (t - x0)
                y = need_y if y is None else max(y, need_y)
            y = _up(max(room, min(y, y0))) if y is not None else _up(room)    # never warmer towards milder weather
        points.append([x, y, made_at])
        if y is not None:
            prev = (x, y)
    out_days = [t for t, _e in res]
    reliable = len(res) >= RELIABLE_DAYS and len(steady) >= RELIABLE_HOURS and se / ua < RELIABLE_SE
    return CurveAdvice(points=points, room=room, ua_kw=round(ua, 4), base_kw=round(base, 3), margin_kw=round(margin, 3),
                       k_kw=round(k, 4), n=n, cycling_from=None if cycling is None else round(cycling, 1), days=len(res),
                       hours=len(steady), out_min=round(min(out_days), 1), out_max=round(max(out_days), 1),
                       reliable=reliable, extrapolated=[x for x in xs if x < min(out_days)],
                       measured_by=measured_by(rows, flows, opentherm or set()),
                       cloud=[[round(o, 1), round(f, 1)] for o, _t, f, _q in steady[::max(1, -(-len(steady) // CLOUD_MAX))]],
                       cold_hour=round(min(r.T_out for r in rows if r.Q >= 0.3), 1) if any(r.Q >= 0.3 for r in rows) else None)


def opentherm_from_hours(hours: dict[int, dict]) -> set[int]:
    """Hours in which an OpenTherm thermostat asked the unit for a water temperature (the CIC's control setpoint, key 'th_water')."""
    return {t for t, v in hours.items() if v.get("th_water")}


def flows_from_hours(hours: dict[int, dict]) -> dict[int, float]:
    """{hour ts: flow °C} from the unit's hours (key 'flow': the water to the house)."""
    return {t: v["flow"] for t, v in hours.items() if v.get("flow") is not None}


def made_note(advice: CurveAdvice, now: float) -> dict:
    """A short summary for the logs and the diagnostics."""
    return {"at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(timespec="seconds"), "days": advice.days,
            "hours": advice.hours, "reliable": advice.reliable, "points": advice.points}
