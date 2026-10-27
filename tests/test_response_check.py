"""Response to the thermostat, hot water profile, self-check and the correction from the last hours."""
import math
import os
from datetime import datetime, timezone
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core import load, run_all  # noqa: E402

model = load("model")
heatpump = load("heatpump")
planner = load("planner")
response = load("response")
check = load("check")

DAY0 = 20_000
HOUSE = model.HouseModel(C=19.0, H=0.125, g=5.5, lag=1.0, internal=-0.05, Hw=0.007, source="learned")


def simulate(hp, days=30, seed=5, house=HOUSE):
    """Hourly rows of a house driven by a thermostat with the given response: day 20.5 °C, night 19 °C, and now and
    then a different setpoint, as someone (or a planner) would set. Rows hold hourly means, like the heat pump's hours."""
    rnd = random.Random(seed)
    sim = planner.Simulator(house, hp, planner.Settings())
    rows, T, E, w = [], 20.0, 0.0, 1.0
    for d in range(days):
        for h in range(24):
            sp = 20.5 if 7 <= h < 22 else 19.0
            if rnd.random() < 0.15:
                sp += rnd.choice((-1.0, -0.5, 0.5, 1.0))
            t_out = 4 + 4 * math.sin((h - 9) / 24 * 2 * math.pi) + rnd.uniform(-1, 1)
            rad = max(0.0, 0.35 * math.sin((h - 7) / 11 * math.pi)) if 7 <= h <= 18 else 0.0
            wind = 3.5 + rnd.uniform(-2, 3)
            hin = planner.HourIn(t_out=t_out, wind=wind, rad=rad, p_grid=0.0, p_own=0.0)
            T1, E1, _c, e, q, _p = sim.hour(T, E, sp, hin, w)
            w = sim.w_end
            rows.append(model.HourRow(ts=(DAY0 + d) * 86400 + h * 3600, T=(T + T1) / 2, T_out=t_out, Q=q, rad=rad, wind=wind, E=e,
                                      T_out_sensor=t_out + 1.0, heating_s=3600.0 if q > 0.3 else 0.0, sp=sp,
                                      T_th=(T + T1) / 2 + hp.th_diff, room_sensor=True))
            T, E = T1, E1
    return rows


def true_pump():
    """Like the author's Lyric T6 (OpenTherm) on a Blackbird P80: modulating, about 1 kW per degree, slow."""
    hp = heatpump.HeatPumpModel()
    hp.a, hp.k, hp.offset, hp.follow, hp.th_diff = 0.9, 1.0, 0.4, 0.35, -0.8
    return hp


def test_response_learned_from_setpoints_and_heat():
    rows = simulate(true_pump())
    m, note = response.learn(rows, HOUSE, heatpump.HeatPumpModel())
    assert m.resp_source == "learned", note
    assert m.th_diff == -0.8, note
    assert abs(m.k - 1.0) <= 0.5 and abs(m.offset - 0.4) <= 0.3 and 0.25 <= m.follow <= 0.5 and abs(m.a - 0.9) <= 0.15, note
    assert m.resp_error is not None and m.resp_error < 0.1, m.resp_error


def test_response_leaves_the_cop_alone():
    hp = heatpump.HeatPumpModel()
    before = hp.cop(3.0, 2.0)
    m, _ = response.learn(simulate(true_pump()), HOUSE, hp)
    assert m.cop(3.0, 2.0) == before and m.alpha == hp.alpha          # alpha is the COP's, the delay is `follow`


def test_response_skips_days_without_heating():
    rows = simulate(true_pump(), days=20)
    for r in rows[-10 * 24:]:                    # heating switched off for the last ten days (summer)
        r.Q, r.E, r.heating_s = 0.0, 0.0, 0.0
    m, note = response.learn(rows, HOUSE, heatpump.HeatPumpModel())
    assert m.resp_source == "learned" and m.k >= 0.5, note


def test_a_heat_pump_on_its_own_curve_has_no_lever():
    hp = true_pump()
    hp.k = 0.0                                   # the setpoint does nothing (heating curve)
    m, note = response.learn(simulate(hp), HOUSE, heatpump.HeatPumpModel())
    assert m.resp_source == "learned" and m.k < 0.2, note
    assert check.readiness({"heating_hours": 100, "rmse_6h": 0.2, "heat_ratio": 1.0}, True, lever=False) == (False, ["lever"])


def test_response_needs_hours_with_a_setpoint():
    rows = simulate(true_pump(), days=2)
    for r in rows:
        r.sp = None
    m, note = response.learn(rows, HOUSE, heatpump.HeatPumpModel())
    assert m.resp_source == "default" and "usable windows" in note


def test_hot_water_blocks_space_heating():
    hp = heatpump.HeatPumpModel()
    sim = planner.Simulator(HOUSE, hp, planner.Settings())
    cold = dict(t_out=-5.0, wind=3.5, rad=0.0, p_grid=0.3, p_own=0.3)
    q_free = sim.hour(18.0, 0.0, 21.0, planner.HourIn(**cold))[4]
    q_dhw = sim.hour(18.0, 0.0, 21.0, planner.HourIn(**cold, dhw=0.75))[4]
    assert q_dhw < q_free * 0.4, (q_free, q_dhw)


def test_cycling_costs_more_per_kwh():
    hp = heatpump.HeatPumpModel()
    sim = planner.Simulator(HOUSE, hp, planner.Settings())
    mild = planner.HourIn(t_out=14.0, wind=3.5, rad=0.0, p_grid=0.3, p_own=0.3)
    _T, _E, c1, e1, q1, _ = sim.hour(20.4, 0.0, 20.5, mild)
    hp.q_min, hp.cyc = 4.0, 0.7
    _T, _E, c2, e2, q2, _ = sim.hour(20.4, 0.0, 20.5, mild)
    assert abs(q1 - q2) < 1e-9 and q1 > 0 and e2 > e1 * 1.3


def test_hot_water_profile():
    samples = []
    for week in range(4):
        for wd in range(7):
            for h in range(24):
                share = 0.75 if h == 13 else (1.0 if (wd == 6 and h == 12) else 0.0)
                samples.append((wd, h, share))
    prof = response.dhw_profile(samples)
    assert len(prof) == 168 and prof[13] == 0.75 and prof[6 * 24 + 12] == 1.0 and prof[12] == 0.0
    assert response.dhw_profile(samples[:100]) is None
    hp = heatpump.HeatPumpModel(dhw=prof)
    assert hp.dhw_share(6, 12) == 1.0 and hp.dhw_share(2, 3) == 0.0


def test_self_check_and_readiness():
    hp = true_pump()
    rows = simulate(hp, days=12)
    good = check.self_check(rows, HOUSE, hp)
    assert good["rmse_1h"] < 0.05 and good["rmse_6h"] < 0.1 and abs(good["heat_ratio"] - 1) < 0.05, good
    ready, missing = check.readiness(good, True)
    assert ready and not missing
    wrong = model.HouseModel.from_dict({**HOUSE.as_dict(), "H": 0.25})        # twice the heat loss
    bad = check.self_check(rows, wrong, hp)
    assert bad["rmse_6h"] > good["rmse_6h"] * 3 and bad["heat_ratio"] > 1.3, bad
    assert check.readiness(good, False) == (False, ["following"])
    assert "heat" in check.readiness(bad, True)[1]


def test_self_check_falls_back_to_the_last_week_with_heating():
    """After the import in a mild autumn (or summer) the last week has too little heating: check the newest week
    that had enough, so Roost can tell right away whether it is ready."""
    hp = heatpump.HeatPumpModel(a=0.9, k=1.0, offset=0.3, follow=0.35, resp_source="learned")
    rows = simulate(hp, days=20)
    mild = [model.HourRow(**{**r.__dict__, "ts": r.ts + 20 * 86400, "Q": 0.0, "E": 0.0, "heating_s": 0.0}) for r in rows[-10 * 24:]]
    chk = check.self_check(rows + mild, HOUSE, hp)
    assert chk.get("window_end") and chk["window_end"] <= rows[-1].ts, chk
    assert chk["heating_hours"] >= check.READY_HEATING_HOURS and chk["heating_per_day"] == 0, chk
    assert "rmse_6h" in chk and "heat_ratio" in chk
    assert not check.self_check(rows, HOUSE, hp).get("window_end")          # enough heating lately: the last week
    summer = [model.HourRow(**{**r.__dict__, "ts": r.ts + 70 * 86400, "Q": 0.0, "E": 0.0, "heating_s": 0.0}) for r in rows[-24 * 64:]]
    late = check.self_check(rows + summer, HOUSE, hp)                       # only heating over two months ago: not used
    assert not late.get("window_end") and late["heating_hours"] == 0, late


def test_heating_without_the_thermostat_is_left_out():
    """A unit that also runs on its own heating curve heats with the room well above the setpoint: those hours are not
    the thermostat's doing, so the response and the self-check leave them out; ordinary hours are never flagged."""
    hp = true_pump()
    rows = simulate(hp, days=20)
    assert not model.unfollowed(rows, HOUSE, hp)
    warm = [model.HourRow(**{**r.__dict__, "T": r.sp + 5.0, "T_th": r.sp + 5.0 + hp.th_diff, "Q": 3.0})
            if r.ts // 86400 == rows[-1].ts // 86400 else r for r in rows]
    flagged = model.unfollowed(warm, HOUSE, hp)
    assert len(flagged) >= 12, len(flagged)
    chk = check.self_check(warm, HOUSE, hp)
    assert chk["unfollowed_hours"] == len(flagged) and chk.get("heat_ratio") and abs(chk["heat_ratio"] - 1) < 0.3, chk


def test_mild_weather_is_judged_on_the_last_heating_weeks():
    """Ten heating weeks, then a mild month: the last week says too little, so the newest heating weeks decide —
    and a model that predicts them well is ready to steer."""
    hp = true_pump()
    rows = simulate(hp, days=70)
    mild = [model.HourRow(**{**r.__dict__, "ts": r.ts + 70 * 86400, "Q": 0.0, "E": 0.0, "heating_s": 0.0}) for r in rows[-30 * 24:]]
    every = rows + mild
    chk = check.self_check(every, HOUSE, hp)
    assert chk["heating_hours"] < check.READY_HEATING_HOURS
    assert check.readiness(chk, True)[1][:1] == ["heating_hours"]
    w = check.winter_check(every, HOUSE, hp)
    assert w and w["weeks"] == check.WINTER_WEEKS and check.winter_ok(w), w
    assert check.readiness(chk, True, True, w) == (True, [])
    assert check.readiness(chk, False, True, w) == (False, ["following"])
    bad = heatpump.HeatPumpModel(a=0.3, k=4.0, offset=-0.5, follow=1.0, resp_source="learned")
    wb = check.winter_check(every, HOUSE, bad)                              # a wrong response does not pass
    assert not check.winter_ok(wb) and not check.readiness(chk, True, True, wb)[0], wb


def test_heating_weeks_verdict():
    good = {"weeks": 8, "passed": 5, "rmse_6h": 0.45, "heat_ratio": 1.13}
    assert check.winter_ok(good)                                               # one odd week more does not flip it
    assert not check.winter_ok({**good, "passed": 3})                          # too few weeks pass on their own
    assert not check.winter_ok({**good, "rmse_6h": 0.6})                       # the median is off
    assert not check.winter_ok({**good, "heat_ratio": 1.4}) and not check.winter_ok(None)


def test_expected_ready():
    now, night = 1_000_000.0, 1_050_000.0
    assert check.eta([], {}, {}, now, night) == ("ready", None)
    assert check.eta(["following", "temperature"], {}, {}, now, night) == ("following", None)
    code, ts = check.eta(["temperature"], {}, {"status": "importing", "months": 12, "months_done": 2}, now, night)
    assert code == "import" and ts == now + 10 * check.ETA_MONTH_S + check.ETA_LEARN_S
    assert check.eta(["heating_hours"], {"heating_hours": 10, "heating_per_day": 0.3}, {}, now, night) == ("heating_season", None)
    assert check.eta(["heating_hours"], {"heating_hours": 9, "heating_per_day": 2.0, "days": 7}, {}, now, night) == ("heating_season", None)
    assert check.eta(["heating_hours"], {"heating_hours": 10, "heating_per_day": 8}, {}, now, night) == ("heating", night + 2 * 86400)
    assert check.eta(["temperature", "heat"], {}, {}, now, night) == ("check", night)


def test_correction_from_the_last_hours():
    hp = heatpump.HeatPumpModel()
    sim = planner.Simulator(HOUSE, hp, planner.Settings())
    t0 = 1_800_000_000 - 1_800_000_000 % 3600
    entries, T, E = [], 21.0, 0.5
    for k in range(6):
        h = planner.HourIn(t_out=12.0, wind=3.5, rad=0.0, p_grid=0.0, p_own=0.0)
        T1, E1, *_ = sim.hour(T, E, 20.5, h)
        entries.append({"ts": t0 + k * 3600, "T": T, "E": E, "sp_t": 20.5, "t_out": 12.0, "wind": 3.5, "rad": 0.0, "dhw": 0.0})
        T, E = T1 + 0.02, E1                     # the room ends each hour 0.02 °C warmer than the model says
    entries.append({"ts": t0 + 6 * 3600, "T": T, "E": E, "sp_t": 20.5, "t_out": 12.0})
    kw, n = check.correction(entries, HOUSE, hp, t0 + 6 * 3600)
    assert n == 6 and 0.25 < kw < 0.4, (kw, n)   # 0.02 °C × 19 kWh/K = 0.38 kW, shrunk for 6 hours
    assert check.fade(kw, 6) == kw / 2
    for e in entries:
        e.pop("dhw", None)                       # hot water unknown: no correction
    assert check.correction(entries, HOUSE, hp, t0 + 6 * 3600) == (0.0, 0)
    for e in entries:
        e["dhw"] = 0.0
        e["window"] = True                       # airing: left out as well
    assert check.correction(entries, HOUSE, hp, t0 + 6 * 3600) == (0.0, 0)


def test_sunny_hours_are_left_out():
    """The room got warmer than predicted in sunny hours (low autumn sun on the facade): that is the sun model's, not
    something to carry ahead. Until v0.7.7 it became extra sun for a day; on a year of the author's data that made the
    forecasts 6–24 hours ahead worse (and before v0.5.3, as a constant, 1 kW all night)."""
    hp = heatpump.HeatPumpModel()
    sim = planner.Simulator(HOUSE, hp, planner.Settings())
    t0 = 1_800_000_000 - 1_800_000_000 % 3600
    entries, T, E = [], 22.0, 0.0
    for k in range(8):
        rad = 0.3
        h = planner.HourIn(t_out=14.0, wind=3.5, rad=rad, p_grid=0.0, p_own=0.0)
        T1, E1, *_ = sim.hour(T, E, 19.0, h)
        entries.append({"ts": t0 + k * 3600, "T": T, "E": E, "sp_t": 19.0, "t_out": 14.0, "wind": 3.5, "rad": rad, "dhw": 0.0})
        T, E = T1 + 1.5 * rad / HOUSE.C, E1      # 1.5 m² more sun than the model has
    entries.append({"ts": t0 + 8 * 3600, "T": T, "E": E, "sp_t": 19.0, "t_out": 14.0})
    assert check.correction(entries, HOUSE, hp, t0 + 8 * 3600) == (0.0, 0)


def test_a_thermostat_in_half_degrees_gives_no_correction():
    """Only the thermostat as room temperature (a Lyric T6 shows 0.5 °C steps): the room held at '20.0' for six hours
    while a room sensor saw it fall 20.4 → 20.0. The correction made that +0.66 kW of free heat (a sensor would have
    given −0.5 kW) and the plan hardly heated (author's house, 23-10-2026). A step of 0.5 °C in an hour is 7 kW."""
    hp = heatpump.HeatPumpModel()
    t0 = 1_800_000_000 - 1_800_000_000 % 3600
    temps = [21.0, 21.0, 20.5, 20.5, 20.5, 20.0, 20.0, 20.0, 20.0]
    entries = [{"ts": t0 + k * 3600, "T": v, "E": 0.0, "sp_t": 20.0, "t_out": 10.0, "wind": 3.5, "rad": 0.0, "dhw": 0.0}
               for k, v in enumerate(temps)]
    assert check.correction(entries, HOUSE, hp, t0 + 8 * 3600) == (0.0, 0)
    for e, v in zip(entries, [21.1, 21.0, 20.8, 20.7, 20.6, 20.5, 20.4, 20.3, 20.3]):
        e["T"] = v                               # the room sensor: a correction again
    assert check.correction(entries, HOUSE, hp, t0 + 8 * 3600)[1] == 8



def test_slow_unit_plan_beats_a_steady_thermostat():
    """A modulating unit that follows slowly: the plan (search + polish with the real delay) keeps the room within
    comfort and saves against the steady thermostat; with a steep evening (70 ct) it coasts through it on far less
    electricity. (Until v0.7.0 polish counted the heat left at the end the wrong
    way round; v0.7.0 fixed that but kept a switching cost tuned to the old count, so a slow unit hardly moved.)"""
    hp = true_pump()
    s = planner.Settings(comfort=20.5, day_min=20.0, night_min=19.0, store_max=22.5)
    for evening_price in (0.45, 0.70):
        hours = []
        for i in range(36):
            hr = (13 + i) % 24
            price = 0.22 if 10 <= hr < 16 else (evening_price if 17 <= hr < 21 else (0.25 if hr >= 21 or hr < 7 else 0.30))
            hours.append(planner.HourIn(t_out=2 + 2 * math.sin((hr - 9) / 24 * 2 * math.pi), wind=4, rad=0.15 if 10 <= hr <= 15 else 0,
                                        p_grid=price, p_own=price, day=7 <= hr < 22, hour=hr))
        p = planner.plan(HOUSE, hp, s, hours, 20.6, 1.0, 20.0, w_now=2.0)
        assert p.saving > 0.0, (evening_price, p.saving)
        assert all(x.t_end >= 20.1 for x, h in zip(p.hours, hours) if h.day), [round(x.t_end, 2) for x in p.hours]
    ev = [r for r in p.breakdown["hours"] if 17 <= r["hour"] < 21]
    assert sum(r["kwh"] for r in ev) < 0.7 * sum(r["b_kwh"] for r in ev), ev          # 70 ct: far less in the evening
    assert min(x.sp for x, h in zip(p.hours, hours) if 15 <= h.hour < 20) < 19.5, [x.sp for x in p.hours]    # 70 ct: coasts


def test_steady_comparison_is_exactly_as_comfortable():
    """#5: on 0.5 °C steps the steady thermostat one step lower fell a hair short of the plan's comfort, so a whole
    step higher was taken (21 °C all day for a 20.5 °C comfort) and the plan seemed to save what that step costs. The
    two steps are weighed to the plan's comfort now."""
    hp = true_pump()
    s = planner.Settings(comfort=20.5, day_min=20.0, night_min=19.0, store_max=22.5)
    hours = []
    for i in range(36):
        hr = (13 + i) % 24
        price = 0.22 if 10 <= hr < 16 else (0.45 if 17 <= hr < 21 else (0.25 if hr >= 21 or hr < 7 else 0.30))
        hours.append(planner.HourIn(t_out=2 + 2 * math.sin((hr - 9) / 24 * 2 * math.pi), wind=4, rad=0.15 if 10 <= hr <= 15 else 0,
                                    p_grid=price, p_own=price, day=7 <= hr < 22, hour=hr))
    bd = planner.plan(HOUSE, hp, s, hours, 20.6, 1.0, 20.0, w_now=2.0).breakdown
    assert abs(bd["b_short"] - bd["short"]) < 0.02, (bd["short"], bd["b_short"])      # whole steps: 0.18 against 0.08
    assert abs(sum(r["save"] for r in bd["hours"]) + bd["b_end"] - bd["end"] - bd["saving"]) < 0.01


def test_import_end_expected_from_the_months_left():
    """The import reads Home Assistant's own statistics: seconds per month."""
    imp = {"months": 12, "months_done": 2, "at": "2026-10-20T09:45:00+00:00"}
    at = datetime(2026, 10, 20, 9, 45, tzinfo=timezone.utc).timestamp()
    assert check.import_done_at(imp, at) == at + 10 * check.ETA_MONTH_S


if __name__ == "__main__":
    run_all(dict(globals()))
