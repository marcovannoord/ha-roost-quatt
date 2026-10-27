"""The plan held (stick.py): Roost keeps its setpoints until something real changes. And the unit stopping at once
when the thermostat asks nothing (heatpump.HeatPumpModel.stops), the cause of the short bursts it replaces."""
import math

from core import load, run_all

stick = load("stick")
planner = load("planner")
heatpump = load("heatpump")
model = load("model")
series = load("series")

H0 = 1_793_000_000 - 1_793_000_000 % 3600


def commitment(**kw):
    c = dict(at=H0 + 600, hour0=H0, sp=[21.5] * 12, room0=20.8, t_end=[20.9 + 0.1 * i for i in range(12)],
             t_out=[8.0] * 12, rad=[0.0] * 12, tariff=[0.30] * 12, pv=[0.0] * 12)
    c.update(kw)
    return stick.Commitment(**c)


def why(c, now, **kw):
    args = dict(room=c.expected_room(now) if c else 20.8, coarse=False, tariff=c.tariff[c.offset(now):] if c else [0.3],
                t_out=[8.0] * 6, rad=[0.0] * 6, pv=[0.0] * 6, pv_now_kw=None, watch=stick.Watch())
    args.update(kw)
    return stick.why_plan(c, now, **args)


def test_nothing_changed_keeps_the_plan():
    c = commitment()
    for minutes in (20, 75, 190):
        assert why(c, H0 + minutes * 60) is None


def test_expected_room_runs_from_the_plan_start_to_each_hour_end():
    c = commitment()
    assert abs(c.expected_room(H0 + 600) - 20.8) < 1e-9
    assert abs(c.expected_room(H0 + 3600) - 20.9) < 1e-9
    assert abs(c.expected_room(H0 + 5400) - 20.95) < 1e-9
    assert c.setpoints(H0 + 2 * 3600 + 5) == [21.5] * 10


def test_reasons_to_plan_afresh():
    c = commitment()
    t = H0 + 2 * 3600 + 900
    assert why(None, t) == "first"
    assert why(c, t, force="settings") == "settings"
    assert why(c, H0 + 12 * 3600 + 5) == "horizon"
    assert why(commitment(sp=[21.5] * 24, t_end=[21.0] * 24), H0 + 600 + stick.MAX_AGE_H * 3600) == "age"
    assert why(c, t, tariff=[0.30] * 10 + [0.25] * 3) == "prices"          # tomorrow's prices are in
    full = commitment(sp=[21.5] * 24, t_end=[21.0] * 24, tariff=[0.30] * 36)
    assert why(full, H0 + 5 * 3600, tariff=[0.30] * 36) is None           # a full horizon (a fixed contract) moves on
    assert why(c, t, tariff=[0.30, 0.45] + [0.30] * 8) == "prices"         # a price in the plan changed
    assert why(c, t, t_out=[10.5] * 6) == "weather"
    assert why(c, t, rad=[0.3] * 6) == "sun"
    assert why(c, t, pv=[0.5] * 6) == "solar"
    assert why(c, t, pv_now_kw=2.0) == "solar"
    assert why(commitment(fallback="no_price"), t) == "prices"            # prices are back after a fallback


def test_a_room_off_the_plan_needs_two_checks_and_more_for_a_coarse_reading():
    c = commitment()
    t = H0 + 3 * 3600
    w = stick.Watch()
    off = c.expected_room(t) - 0.5
    assert why(c, t, room=off, watch=w) is None
    assert why(c, t + 120, room=off, watch=w) == "room"
    w = stick.Watch()
    assert why(c, t, room=off, coarse=True, watch=w) is None and why(c, t + 120, room=off, coarse=True, watch=w) is None


def test_commitment_survives_storage():
    c = commitment(fallback="no_price")
    assert stick.Commitment.from_dict(c.as_dict()) == c
    assert stick.Commitment.from_dict(None) is None and stick.Commitment.from_dict({"bogus": 1}) is None


def test_pv_mean_needs_a_quarter_of_an_hour():
    w = stick.Watch()
    assert w.feed_pv(0, 1.0) is None
    assert w.feed_pv(600, 3.0) is None
    assert abs(w.feed_pv(13 * 60, 2.0) - 2.0) < 1e-9


HOUSE = model.HouseModel(C=14.7, H=0.1675, g=3.4, lag=0.81, internal=0.64)


def test_the_unit_stops_at_once_when_the_thermostat_asks_nothing():
    """A setpoint well below the room (the thermostat asks nothing): no heat after it, though the unit ran at 6 kW (it
    slowly faded before v0.8.0)."""
    hp = heatpump.HeatPumpModel(a=1.0, k=1.0, offset=0.1, follow=0.35, th_diff=-0.2)
    s = planner.Settings(comfort=21.0, day_min=19.0, night_min=19.0, store_max=25.0)
    h = planner.HourIn(t_out=10.0, wind=3.5, rad=0.0, p_grid=0.3, p_own=0.3, day=False, hour=2)
    sim = planner.Simulator(HOUSE, hp, s)
    _T, _E, _c, kwh, heat, _p = sim.hour(20.9, 1.0, 19.0, h, 6.2)
    assert heat == 0.0 and kwh == 0.0
    hp.stops = False
    sim = planner.Simulator(HOUSE, hp, s)
    _T, _E, _c, kwh, heat, _p = sim.hour(20.9, 1.0, 19.0, h, 6.2)
    assert heat > 3.0                                           # the old fade: free heat the unit never gave
    hp.stops = True
    sim = planner.Simulator(HOUSE, hp, s)
    _T, _E, _c, _kwh, heat, _p = sim.hour(20.9, 1.0, 21.5, h, 0.0)
    assert 0.0 < heat < 2.0                                     # rising still follows the learned delay


def test_a_running_unit_no_longer_makes_the_plan_lower_the_setpoint():
    """The night of 26-27 October 2026: with the unit running the plan lowered the setpoint, the unit stopped, the
    next plan raised it again. With the unit stopping at once the plan is the same running or not."""
    hp = heatpump.HeatPumpModel(a=1.0, k=1.0, offset=0.1, follow=0.35, th_diff=-0.2, alpha=3.4, beta=0.25, gamma=-0.55)
    s = planner.Settings(comfort=21.0, day_min=19.0, night_min=19.0, store_max=25.0, sp_min=19.0)
    hours = [planner.HourIn(t_out=12.0 - 2 * math.cos(i / 24 * 2 * math.pi), wind=3.5, rad=0.0,
                            p_grid=0.24 if i < 6 else 0.30 if i < 16 else 0.45, p_own=0.24, day=7 <= (i + 1) % 24 < 21,
                            hour=(i + 1) % 24) for i in range(24)]
    first = {w: planner.plan(HOUSE, hp, s, hours, 20.9, 1.0, 21.5, 24, w).hours[0].sp for w in (0.0, 6.2)}
    assert first[0.0] == first[6.2], first


def test_a_held_plan_keeps_its_setpoints():
    hp = heatpump.HeatPumpModel(a=1.0, k=1.0, offset=0.1, follow=0.35)
    s = planner.Settings(comfort=21.0, day_min=19.0, night_min=19.0, store_max=25.0)
    hours = [planner.HourIn(t_out=8.0, wind=3.5, rad=0.0, p_grid=0.3, p_own=0.3, day=True, hour=(9 + i) % 24) for i in range(30)]
    fixed = [20.0, 20.5, 21.0] * 3
    p = planner.plan(HOUSE, hp, s, hours, 20.8, 0.5, 20.0, 24, 0.0, fixed=fixed)
    assert [x.sp for x in p.hours] == fixed + [fixed[-1]] * 15
    assert p.breakdown["quality"]["reasons"] == [] or "comfort_mismatch" in p.breakdown["quality"]["reasons"]


def test_extra_rooms_counted_as_configured():
    """R08: a configured room without a reading still makes the saving not whole-house."""
    hp = heatpump.HeatPumpModel(a=1.0, k=1.0, offset=0.1, follow=0.35)
    s = planner.Settings(comfort=21.0, day_min=19.0, night_min=19.0, store_max=25.0)
    hours = [planner.HourIn(t_out=8.0, wind=3.5, rad=0.0, p_grid=0.3, p_own=0.3, day=True, hour=(9 + i) % 24) for i in range(24)]
    p = planner.plan(HOUSE, hp, s, hours, 20.8, 0.5, 20.0, 24, 0.0, None, extra_rooms=1)
    assert "extra_rooms" in p.breakdown["quality"]["reasons"]


def test_price_history_classification_and_fit():
    lh = lambda ts: (ts // 3600) % 24
    assert series.classify_history({h * 3600: 0.3 for h in range(5)}, lh) == "unknown"
    assert series.classify_history({h * 3600: 0.3 for h in range(30)}, lh) == "flat"
    assert series.classify_history({h * 3600: 0.2 if h % 24 < 7 else 0.3 for h in range(48)}, lh) == "tou"
    assert series.classify_history({h * 3600: 0.1 + 0.01 * (h % 5) for h in range(48)}, lh) == "dynamic"
    a, b, r2 = series.fit_line([(x / 10, 1.21 * x / 10 + 0.1) for x in range(20)])
    assert abs(a - 1.21) < 1e-9 and abs(b - 0.1) < 1e-9 and r2 > 0.999
    assert series.fit_line([(1.0, 2.0)] * 20) is None


if __name__ == "__main__":
    run_all(globals())
