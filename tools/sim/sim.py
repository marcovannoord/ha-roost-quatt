"""Closed-loop simulation of Roost against a "true" house that differs from what Roost knows.

    python3 tools/sim/sim.py            all scenarios in parallel, a table at the end
    python3 tools/sim/sim.py home 3     one scenario, 3 days

Per scenario:
1. 40 days of history from the true house under an ordinary thermostat schedule (with now and then a change by hand);
   Roost learns its house model and the heat pump's response from it, as it does in Home Assistant.
2. N days closed loop: every hour Roost plans 36 h ahead with a weather FORECAST (an error that grows with the hours
   ahead), its control rules apply (at most one change an hour), the correction from the last hours is on; the true
   house then runs that hour with the real weather, random internal gains and the true heat pump response.
3. The same days with a steady thermostat (holding the comfort temperature) in the same true house.
Reported: cost, kWh, degree-hours below comfort in the comfort hours, hours below the minimum, lowest room
temperature, thermostat changes, and for an extra room its hours below its minimum.
"""
from __future__ import annotations

import json
import math
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field, replace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tests"))
from core import load  # noqa: E402

model = load("model")
heatpump = load("heatpump")
planner = load("planner")
control = load("control")
check = load("check")
response = load("response")
rooms_mod = load("rooms")
value = load("value")
stick = load("stick")

# A/B switches: SIM_FADE=1 Roost plans as if the unit's output fades after the thermostat stops asking (before v0.8.0;
# the true unit stops at once), SIM_HOLD=1 the plan is held between reasons to plan afresh (stick.py, v0.8.0)
FADE = os.environ.get("SIM_FADE") == "1"
HOLD = os.environ.get("SIM_HOLD") == "1"

DAY0 = 20_450                     # 2025-12-29 (a Monday)
HIST_DAYS = 40


@dataclass
class Scenario:
    name: str
    house: dict                                    # true house parameters (model.HouseModel fields)
    pump: dict                                     # true response (heatpump.HeatPumpModel fields)
    t_mean: float = 3.0                            # outdoor mean (°C); daily swing ±4
    weeks: list | None = None                      # outdoor mean per week of the run instead (a winter month)
    sun: float = 0.25                              # peak global radiation on a clear day (kW/m²)
    prices: str = "dynamic"                        # dynamic | fixed | double
    forecast_sd: float = 1.0                       # °C forecast error after 24 h
    learned_bias: dict = field(default_factory=dict)   # after learning, multiply these true values (a model that is off)
    room: dict | None = None                       # an extra room: {"model": {...}, "min": .., "from": .., "to": ..}
    before: dict | None = None                     # the house before a change (insulation): its history comes first
    before_days: int = 0
    settings: dict = field(default_factory=dict)
    pump_bias: dict = field(default_factory=dict)  # after learning, multiply these true response values
    own_curve: float = 0.0                         # history only: share of warm hours the unit heats on its own curve
    learned_set: dict = field(default_factory=dict)   # after learning, set these house values (a fast house learned as fast)


SCENARIOS = {
    "home": Scenario("home: floor heating, slow OpenTherm unit, dynamic price, January",
                     dict(C=18.0, H=0.15, g=5.0, lag=1.0, internal=0.2, Hw=0.007),
                     dict(a=0.9, k=1.0, offset=0.3, follow=0.35, th_diff=-0.2, q_min=2.4)),
    "radiators": Scenario("radiators: fast unit, small buffer",
                          dict(C=12.0, H=0.16, g=4.0, lag=0.15, internal=0.2, Hw=0.007),
                          dict(a=0.95, k=3.0, offset=0.1, follow=0.8, q_min=2.0, alpha=2.4)),
    "fixed": Scenario("fixed price, single rate", dict(C=18.0, H=0.15, g=5.0, lag=1.0, internal=0.2, Hw=0.007),
                      dict(a=0.9, k=1.0, offset=0.3, follow=0.35, q_min=2.4), prices="fixed"),
    "double": Scenario("fixed price with a night/weekend rate", dict(C=18.0, H=0.15, g=5.0, lag=1.0, internal=0.2, Hw=0.007),
                       dict(a=0.9, k=1.0, offset=0.3, follow=0.35, q_min=2.4), prices="double"),
    "mismatch": Scenario("model off: house loses 30 % more than learned, larger forecast error",
                         dict(C=18.0, H=0.15, g=5.0, lag=1.0, internal=0.2, Hw=0.007),
                         dict(a=0.9, k=1.0, offset=0.3, follow=0.35, q_min=2.4), forecast_sd=2.5, learned_bias={"H": 1 / 1.3}),
    "spring": Scenario("spring: mild and sunny", dict(C=18.0, H=0.15, g=5.0, lag=1.0, internal=0.2, Hw=0.007),
                       dict(a=0.9, k=1.0, offset=0.3, follow=0.35, q_min=2.4), t_mean=9.0, sun=0.6),
    "onoff": Scenario("on/off thermostat, heating curve when asked", dict(C=16.0, H=0.15, g=4.0, lag=0.6, internal=0.2, Hw=0.007),
                      dict(a=1.0, k=None, offset=0.0, follow=1.0, q_min=2.5)),
    "insulated": Scenario("insulated since last winter: 90 days of the old house (0.22 kW/K), then 40 of the new (0.12)",
                          dict(C=18.0, H=0.12, g=5.0, lag=1.0, internal=0.2, Hw=0.007),
                          dict(a=0.9, k=1.0, offset=0.3, follow=0.35, q_min=2.4),
                          before=dict(C=18.0, H=0.22, g=5.0, lag=1.0, internal=0.2, Hw=0.007), before_days=90),
    "old": Scenario("1930s house, poorly insulated, radiators, fast unit", dict(C=13.0, H=0.28, g=3.0, lag=0.2, internal=0.2, Hw=0.012),
                    dict(a=0.95, k=3.0, offset=0.1, follow=0.8, q_min=2.0)),
    "newbuild": Scenario("new build: well insulated, heavy floor, much glass; the unit is oversized (cycles)",
                         dict(C=24.0, H=0.07, g=7.0, lag=2.0, internal=0.3, Hw=0.003),
                         dict(a=0.9, k=1.0, offset=0.3, follow=0.35, q_min=2.4), sun=0.35),
    "apartment": Scenario("apartment: small, little storage, warm neighbours", dict(C=7.0, H=0.07, g=2.0, lag=0.4, internal=0.45, Hw=0.004),
                          dict(a=0.9, k=2.0, offset=0.2, follow=0.6, q_min=1.5)),
    "cold": Scenario("cold snap: −4 °C mean, the unit near its maximum", dict(C=18.0, H=0.15, g=5.0, lag=1.0, internal=0.2, Hw=0.007),
                     dict(a=0.9, k=1.0, offset=0.3, follow=0.35, q_min=2.4), t_mean=-4.0),
    "volatile": Scenario("volatile dynamic price: cheap windy nights, steep evening peaks, cheap sunny noons",
                         dict(C=18.0, H=0.15, g=5.0, lag=1.0, internal=0.2, Hw=0.007),
                         dict(a=0.9, k=1.0, offset=0.3, follow=0.35, q_min=2.4), prices="volatile"),
    "slowpump": Scenario("response off: the unit follows twice as slowly as learned, half the gain",
                         dict(C=18.0, H=0.15, g=5.0, lag=1.0, internal=0.2, Hw=0.007),
                         dict(a=0.9, k=1.0, offset=0.3, follow=0.35, q_min=2.4), pump_bias={"follow": 2.0, "k": 2.0}),
    "autumn": Scenario("autumn, mild: in the history the unit also heats on its own curve now and then",
                       dict(C=18.0, H=0.15, g=5.0, lag=1.0, internal=0.2, Hw=0.007),
                       dict(a=0.9, k=1.0, offset=0.3, follow=0.35, q_min=2.4), t_mean=9.0, sun=0.4, own_curve=0.25),
    "winter": Scenario("a winter month: weeks of 5, 2, −4 and 6 °C (floor heating, slow OpenTherm unit), 28 days",
                       dict(C=18.0, H=0.15, g=5.0, lag=1.0, internal=0.2, Hw=0.007),
                       dict(a=0.9, k=1.0, offset=0.3, follow=0.35, th_diff=-0.2, q_min=2.4), weeks=[5.0, 2.0, -4.0, 6.0]),
    "winter_rad": Scenario("the same winter month with radiators and a fast unit, 28 days",
                           dict(C=12.0, H=0.16, g=4.0, lag=0.15, internal=0.2, Hw=0.007),
                           dict(a=0.95, k=3.0, offset=0.1, follow=0.8, q_min=2.0, alpha=2.4), weeks=[5.0, 2.0, -4.0, 6.0]),
    "winter_onoff": Scenario("the same winter month with an on/off thermostat, 28 days",
                             dict(C=16.0, H=0.15, g=4.0, lag=0.6, internal=0.2, Hw=0.007),
                             dict(a=1.0, k=None, offset=0.0, follow=1.0, q_min=2.5), weeks=[5.0, 2.0, -4.0, 6.0]),
    "fixed_rad": Scenario("radiators, fast unit, fixed price",
                          dict(C=12.0, H=0.16, g=4.0, lag=0.15, internal=0.2, Hw=0.007),
                          dict(a=0.95, k=3.0, offset=0.1, follow=0.8, q_min=2.0, alpha=2.4), prices="fixed"),
    "issue4": Scenario("issue #4: radiators, fixed price, mild, comfort = minimums = lowest = 20",
                       dict(C=9.0, H=0.13, g=4.0, lag=0.3, internal=0.2, Hw=0.007),
                       dict(a=1.1, k=1.5, offset=-0.1, follow=0.7, th_diff=0.07, q_min=2.0), prices="fixed", t_mean=9.0,
                       settings=dict(comfort=20.0, day_min=20.0, night_min=20.0, sp_min=20.0)),
    "old_fixed": Scenario("1930s house, radiators, fast unit, fixed price", dict(C=13.0, H=0.28, g=3.0, lag=0.2, internal=0.2, Hw=0.012),
                          dict(a=0.95, k=3.0, offset=0.1, follow=0.8, q_min=2.0), prices="fixed"),
    "bedroom": Scenario("extra bedroom upstairs (radiators) with a minimum in the evening",
                        dict(C=18.0, H=0.15, g=5.0, lag=1.0, internal=0.2, Hw=0.007),
                        dict(a=0.9, k=1.0, offset=0.3, follow=0.35, q_min=2.4),
                        room={"model": dict(b0=0.0, b_heat=0.10, b_out=0.025, b_main=0.03), "min": 17.0, "from": 19, "to": 23}),
    "rad_fast": Scenario("radiators, dynamic, learned lag 0.2", dict(C=12.0, H=0.16, g=4.0, lag=0.15, internal=0.2, Hw=0.007), dict(a=0.95, k=3.0, offset=0.1, follow=0.8, q_min=2.0, alpha=2.4), learned_set={"lag": 0.2}),
    "rad_fixed_fast": Scenario("radiators, fixed, learned lag 0.2", dict(C=12.0, H=0.16, g=4.0, lag=0.15, internal=0.2, Hw=0.007), dict(a=0.95, k=3.0, offset=0.1, follow=0.8, q_min=2.0, alpha=2.4), prices="fixed", learned_set={"lag": 0.2}),
    "rad_double_fast": Scenario("radiators, night rate, learned lag 0.2", dict(C=12.0, H=0.16, g=4.0, lag=0.15, internal=0.2, Hw=0.007), dict(a=0.95, k=3.0, offset=0.1, follow=0.8, q_min=2.0, alpha=2.4), prices="double", learned_set={"lag": 0.2}),
    "rad_volatile_fast": Scenario("radiators, volatile, learned lag 0.2", dict(C=12.0, H=0.16, g=4.0, lag=0.15, internal=0.2, Hw=0.007), dict(a=0.95, k=3.0, offset=0.1, follow=0.8, q_min=2.0, alpha=2.4), prices="volatile", learned_set={"lag": 0.2}),
    "rad_cold_fast": Scenario("radiators, -4 C, fixed, learned lag 0.2", dict(C=12.0, H=0.16, g=4.0, lag=0.15, internal=0.2, Hw=0.007), dict(a=0.95, k=3.0, offset=0.1, follow=0.8, q_min=2.0, alpha=2.4), prices="fixed", t_mean=-4.0, learned_set={"lag": 0.2}),
    "old_fast": Scenario("old house, dynamic, learned lag 0.2", dict(C=13.0, H=0.28, g=3.0, lag=0.2, internal=0.2, Hw=0.012), dict(a=0.95, k=3.0, offset=0.1, follow=0.8, q_min=2.0), learned_set={"lag": 0.2}),
    "old_fixed_fast": Scenario("old house, fixed, learned lag 0.2", dict(C=13.0, H=0.28, g=3.0, lag=0.2, internal=0.2, Hw=0.012), dict(a=0.95, k=3.0, offset=0.1, follow=0.8, q_min=2.0), prices="fixed", learned_set={"lag": 0.2}),
    "issue4_fast": Scenario("issue #4, learned lag 0.29", dict(C=9.0, H=0.13, g=4.0, lag=0.3, internal=0.2, Hw=0.007),
                       dict(a=1.1, k=1.5, offset=-0.1, follow=0.7, th_diff=0.07, q_min=2.0), prices="fixed", t_mean=9.0,
                       settings=dict(comfort=20.0, day_min=20.0, night_min=20.0, sp_min=20.0), learned_set={"lag": 0.29}),
    "issue4_dyn_fast": Scenario("issue #4 house, dynamic price, default comfort, learned lag 0.29", dict(C=9.0, H=0.13, g=4.0, lag=0.3, internal=0.2, Hw=0.007),
                       dict(a=1.1, k=1.5, offset=-0.1, follow=0.7, th_diff=0.07, q_min=2.0), t_mean=9.0, learned_set={"lag": 0.29}),
}


def weather(rnd: random.Random, sc: Scenario, days: int, start_day: int):
    """Hourly (t_out, radiation, wind) for days, with cloudy and clear days."""
    out = {}
    for d in range(days):
        clear = rnd.random()
        mean = sc.t_mean
        if sc.weeks:
            mean = sc.weeks[max(0, min(len(sc.weeks) - 1, (start_day + d - DAY0) // 7))]
        base = mean + rnd.gauss(0, 2.0)
        wind = max(0.5, rnd.gauss(4.0, 1.5))
        for h in range(24):
            ts = (start_day + d) * 86400 + h * 3600
            t = base + 4 * math.sin((h - 9) / 24 * 2 * math.pi)
            rad = max(0.0, sc.sun * clear * math.sin((h - 7) / 10 * math.pi)) if 7 <= h <= 17 else 0.0
            out[ts] = (t, rad, wind)
    return out


def prices(rnd: random.Random, kind: str, ts: int, day_scale: float) -> float:
    h = ts % 86400 // 3600
    wd = (ts // 86400 - 4) % 7               # 0 = Monday (1970-01-01 was a Thursday)
    if kind == "fixed":
        return 0.28
    if kind == "double":
        return 0.24 if (h >= 23 or h < 7 or wd >= 5) else 0.30
    if kind == "volatile":                   # per day: a windy night and/or a sunny noon, a steep evening
        d = ts // 86400
        r = random.Random(d * 7919)
        night, noon, peak = r.uniform(0.08, 0.24), r.uniform(0.02, 0.26), r.uniform(0.40, 0.70)
        if 0 <= h < 6:
            return round(night, 4)
        if 11 <= h < 15:
            return round(noon, 4)
        if 17 <= h < 21:
            return round(peak, 4)
        return round(0.27 * day_scale, 4)
    shape = {0: 0.24, 1: 0.23, 2: 0.22, 3: 0.22, 4: 0.23, 5: 0.25, 6: 0.30, 7: 0.36, 8: 0.35, 9: 0.30, 10: 0.26, 11: 0.23,
             12: 0.22, 13: 0.22, 14: 0.24, 15: 0.27, 16: 0.32, 17: 0.42, 18: 0.46, 19: 0.44, 20: 0.38, 21: 0.33, 22: 0.29, 23: 0.26}[h]
    return round(shape * day_scale, 4)


def true_models(sc: Scenario):
    house = model.HouseModel(**sc.house, source="learned")
    hp = heatpump.HeatPumpModel.for_profile("p80")
    for k, v in sc.pump.items():
        setattr(hp, k, v)
    return house, hp


def internal(rnd: random.Random, h: int) -> float:
    """Extra heat from people and cooking (kW) beyond the house's constant."""
    x = 0.4 if 17 <= h <= 19 else (0.15 if 7 <= h <= 22 else 0.0)
    return x + rnd.gauss(0, 0.1)


def history(sc: Scenario, rnd: random.Random):
    """40 days under a schedule (day 20.5, night 19.5) with changes by hand, from the true house -> model.HourRow list."""
    house, hp = true_models(sc)
    days = HIST_DAYS + sc.before_days
    wx = weather(rnd, sc, days, DAY0 - days)
    old = model.HouseModel(**sc.before, source="learned") if sc.before else house
    change = (DAY0 - HIST_DAYS) * 86400
    sims = {False: planner.Simulator(old, hp, planner.Settings()), True: planner.Simulator(house, hp, planner.Settings())}
    rows, T, E, w = [], 20.0, 1.0, 1.5
    for ts in sorted(wx):
        sim = sims[ts >= change]
        h = ts % 86400 // 3600
        sp = 20.5 if 7 <= h < 22 else 19.5
        if rnd.random() < 0.08:
            sp += rnd.choice((-1.0, -0.5, 0.5, 1.0))
        t, rad, wind = wx[ts]
        hin = planner.HourIn(t_out=t, wind=wind, rad=rad, p_grid=0.3, p_own=0.3, hour=h, extra_kw=internal(rnd, h) - house.internal * 0)
        T1, E1, _c, e, q, _p = sim.hour(T, E, sp, hin, w)
        w = sim.w_end
        if sc.own_curve and T > sp + 0.5 and rnd.random() < sc.own_curve:
            E1, q, e = E1 + 3.0, q + 3.0, e + 0.75     # the unit's own heating curve: heat the thermostat did not ask for
        reading = (T + T1) / 2 + hp.th_diff
        rows.append(model.HourRow(ts=ts, T=(T + T1) / 2 + rnd.gauss(0, 0.03), T_out=t, Q=q, rad=rad, wind=wind, E=e,
                                  T_out_sensor=t + 1.0, heating_s=3600.0 if q > 0.3 else 0.0, sp=sp, T_th=reading,
                                  room_sensor=True, hour=h))
        T, E = T1, E1
    return rows, T, E, w


def learn(sc: Scenario, rows):
    res = model.learn(rows, model.HouseModel(), local_hour=lambda ts: ts % 86400 // 3600)
    house = res.model
    for k, f in sc.learned_bias.items():
        setattr(house, k, getattr(house, k) * f)
    for k, v in sc.learned_set.items():
        setattr(house, k, v)
    pump0 = heatpump.HeatPumpModel.for_profile("p80")
    pump, _ = heatpump.learn(rows, pump0)
    pump, note = response.learn(rows, house, pump)
    for k, f in sc.pump_bias.items():
        setattr(pump, k, getattr(pump, k) * f)
    return house, pump, res.reason, note


def run(name: str, days: int = 7, seed: int = 1) -> dict:
    sc = SCENARIOS[name]
    rnd = random.Random(seed)
    rows, T0, E0, w0 = history(sc, rnd)
    house, pump, house_note, pump_note = learn(sc, rows)
    true_house, true_hp = true_models(sc)
    if FADE:
        pump.stops = False
    over = json.loads(os.environ.get("SIM_SETTINGS", "{}"))       # try planner settings: SIM_SETTINGS='{"switch_cost": 0.15}'
    s = planner.Settings(**{**dict(comfort=20.5, day_min=20.0, night_min=19.0, store_max=22.5, sp_min=19.0), **sc.settings, **over})
    cs = control.ControlSettings()
    truth = planner.Simulator(true_house, true_hp, s)
    wx = weather(rnd, sc, days + 2, DAY0)
    scale = {d: rnd.uniform(0.85, 1.2) for d in range(DAY0, DAY0 + days + 3)}
    price = {ts: prices(rnd, sc.prices, ts, scale[ts // 86400]) for ts in wx}
    gains = {ts: internal(rnd, ts % 86400 // 3600) for ts in wx}
    err_walk = {ts: 0.0 for ts in wx}

    room_true = rooms_mod.RoomModel(**sc.room["model"]) if sc.room else None
    room_known = None
    if sc.room:                                    # Roost learns the room from its history, as in Home Assistant
        samples, Tr = [], 18.0
        for r in rows:
            Tr1 = room_true.step(Tr, r.Q, r.T_out, r.T) + rnd.gauss(0, 0.02)
            samples.append((Tr, Tr1, r.Q, r.T_out, r.T))
            Tr = Tr1
        room_known = rooms_mod.learn(samples) or rooms_mod.RoomModel()

    mean_out = sum(wx[ts][0] for ts in wx) / len(wx)
    fixed_sp = round(planner.baseline_sp(planner.Settings(comfort=20.5), true_hp, true_house,
                                         planner.HourIn(t_out=mean_out, wind=4.0, rad=0, p_grid=0, p_own=0, day=True)) * 2) / 2

    def run_policy(roost: bool, fixed: float | None = None):
        T, E, w, sp_t = T0, E0, w0, 20.5
        Tr = 18.0
        mem = control.ControlMemory()
        log, out = [], {"trace": [], "cost": 0.0, "kwh": 0.0, "deg_below": 0.0, "hours_below_min": 0, "low": 99.0, "changes": 0,
                        "room_below": 0, "room_low": 99.0, "max_sp": 0.0, "starts": 0, "replans": 0}
        held, watch, q_prev = None, stick.Watch(), 0.0
        start = DAY0 * 86400
        for k in range(days * 24):
            ts = start + k * 3600
            h = ts % 86400 // 3600
            day = 7 <= h < 22
            if roost:
                hours = []
                for j in range(36):
                    t2 = ts + j * 3600
                    t, rad, wind = wx.get(t2, wx[max(wx)])
                    fc_err = rnd.gauss(0, sc.forecast_sd * min(1.0, j / 24))
                    p = price.get(t2, price[max(price)])
                    hours.append(planner.HourIn(t_out=t + fc_err, wind=wind, rad=rad * (1 + rnd.gauss(0, 0.2 * min(1, j / 12))),
                                                p_grid=p, p_own=p, day=7 <= (t2 % 86400 // 3600) < 22, hour=t2 % 86400 // 3600,
                                                dhw=0.0))
                corr, _n = check.correction(log, house, pump, ts)
                hours = [replace(x, extra_kw=check.fade(corr, j)) for j, x in enumerate(hours)]
                room_in = None
                if sc.room:
                    act = [rooms_mod.active(x.hour, sc.room["from"], sc.room["to"]) for x in hours]
                    room_in = [{"model": room_known, "T": Tr, "min": sc.room["min"], "active": act}]
                fixed = None
                if HOLD:
                    why = stick.why_plan(held, ts, room=T, coarse=False, tariff=[x.p_grid for x in hours],
                                         t_out=[x.t_out for x in hours[:6]], rad=[x.rad for x in hours[:6]], pv=None,
                                         pv_now_kw=None, watch=watch)
                    fixed = None if why else held.setpoints(ts)
                p = planner.plan(house, pump, s, hours, T, E, sp_t, 24, w, room_in, fixed=fixed or None)
                if HOLD and not fixed:
                    out["replans"] += 1
                    held = stick.Commitment(at=ts, hour0=ts, sp=[x.sp for x in p.hours], room0=T, t_end=[x.t_end for x in p.hours],
                                            t_out=[x.t_out for x in hours], rad=[x.rad for x in hours],
                                            tariff=[x.p_grid for x in hours])
                d = control.decide(ts, p.first.sp, sp_t, T, s.day_min if day else s.night_min, mem, cs, True)
                if d.setpoint is not None and d.setpoint != sp_t:
                    out["changes"] += 1
                    sp_t = d.setpoint
            else:
                sp_t = fixed                       # one setting day and night, as advised for heat pumps
            t, rad, wind = wx[ts]
            hin = planner.HourIn(t_out=t, wind=wind, rad=rad, p_grid=price[ts], p_own=price[ts], day=day, hour=h, extra_kw=gains[ts])
            T1, E1, c, e, q, _pen = truth.hour(T, E, sp_t, hin, w)
            w = truth.w_end
            out["starts"] += q > 0.05 and q_prev <= 0.05
            q_prev = q
            log.append({"ts": ts, "T": T, "E": E, "sp_t": sp_t, "t_out": t, "wind": wind, "rad": rad, "dhw": 0.0, "q": q, "hour": h})
            log = log[-12:]
            if room_true:
                Tr = room_true.step(Tr, q, t, (T + T1) / 2)
                if rooms_mod.active(h, sc.room["from"], sc.room["to"]):
                    out["room_below"] += Tr < sc.room["min"] - 0.3
                    out["room_low"] = min(out["room_low"], Tr)
            out["trace"].append((h, round(price[ts], 3), sp_t, round(T1, 2), round(q, 2), round(e, 2), round(c, 3), round(t, 1)))
            out["cost"] += c
            out["kwh"] += e
            out["max_sp"] = max(out["max_sp"], sp_t)
            if day:
                out["deg_below"] += max(0.0, s.comfort - T1)
            if T1 < (s.day_min if day else s.night_min) - 0.2:
                out["hours_below_min"] += 1
            out["low"] = min(out["low"], T1)
            T, E = T1, E1
        out["end"] = (T, E)
        return out

    r = run_policy(True)
    # the steady thermostat: the lowest single setting that is at least as comfortable as Roost was
    # (comfort deficit in the comfort hours no larger, nor more hours below the minimum)
    b = None
    for sp in [x / 2 for x in range(36, 48)]:
        cand = run_policy(False, sp)
        if cand["deg_below"] <= r["deg_below"] + 0.5 and cand["hours_below_min"] <= r["hours_below_min"]:
            b, fixed_sp = cand, sp
            break
    if b is None:
        fixed_sp = 23.5
        b = run_policy(False, fixed_sp)
    # level the heat left in the house at the end (warmer = heat already paid for): at the mean price and COP
    heat = (r["end"][0] - b["end"][0]) * true_house.C + (r["end"][1] - b["end"][1])
    p_mean = sum(price.values()) / len(price)
    r["cost_level"] = r["cost"] - heat * p_mean / true_hp.cop(mean_out, 3.0)
    b["cost_level"] = b["cost"]
    r["fixed_sp"] = b["fixed_sp"] = fixed_sp
    return {"name": name, "title": sc.name, "roost": r, "steady": b, "house_note": house_note, "pump_note": pump_note,
            "learned": {"H": round(house.H, 3), "C": round(house.C, 1), "lag": round(house.lag, 2), "k": pump.k, "follow": pump.follow,
                        "offset": pump.offset, "a": pump.a}}


def table(results: list[dict]) -> str:
    lines = [f"{'scenario':10} {'cost R':>7} {'cost S':>7} {'saved':>6} {'kWh R':>6} {'kWh S':>6} {'°h<comf R':>9} {'S':>5} "
             f"{'h<min':>5} {'low R':>5} {'low S':>5} {'chg':>4} {'starts':>6} {'maxsp':>5} {'room<':>5}"]
    for x in results:
        r, b = x["roost"], x["steady"]
        sav = (b["cost_level"] - r["cost_level"]) / b["cost_level"] * 100 if b["cost_level"] else 0
        lines.append(f"{x['name']:10} {r['cost_level']:7.2f} {b['cost_level']:7.2f} {sav:5.1f}% {r['kwh']:6.1f} {b['kwh']:6.1f} {r['deg_below']:9.1f} "
                     f"{b['deg_below']:5.1f} {r['hours_below_min']:5d} {r['low']:5.1f} {b['low']:5.1f} {r['changes']:4d} {r['starts']:6d} {r['max_sp']:5.1f} "
                     f"{(str(r['room_below']) + '/' + str(b['room_below'])) if x['name'] == 'bedroom' else '':>5}")
    return "\n".join(lines)


if __name__ == "__main__":
    names = sys.argv[1].split(",") if len(sys.argv) > 1 and sys.argv[1] != "all" else list(SCENARIOS)
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    seed = int(os.environ.get("SIM_SEED", "1"))                    # another week of weather, prices and noise
    with ProcessPoolExecutor(max_workers=len(names)) as ex:
        results = list(ex.map(run, names, [days] * len(names), [seed] * len(names)))
    for x in results:
        print(f"{x['name']}: {x['title']}\n   learned {x['learned']}\n   house: {x['house_note']} | pump: {x['pump_note'][:160]}")
    print(table(results))
