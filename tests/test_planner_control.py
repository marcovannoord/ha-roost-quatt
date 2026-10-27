"""Planner, control and the energy value for the planner."""
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from core import load, run_all  # noqa: E402

model = load("model")
heatpump = load("heatpump")
planner = load("planner")
control = load("control")
value = load("value")
series = load("series")

HOUSE = model.HouseModel(C=19.1, H=0.122, g=5.8, lag=0.98, internal=-0.02, Hw=0.0073, source="learned")
PUMP = heatpump.HeatPumpModel.for_profile("p80")
PRICES = [0.30, 0.27, 0.25, 0.24, 0.25, 0.28, 0.33, 0.38, 0.45, 0.49, 0.46, 0.40, 0.36, 0.33, 0.30, 0.28, 0.27, 0.27, 0.28, 0.30,
          0.31, 0.33, 0.35, 0.33]                     # from 08:00: cheap midday, expensive 16–19 h


def hours(t_out, prices=PRICES, start=8, own=None):
    out = []
    for i, p in enumerate(prices):
        h = (start + i) % 24
        rad = max(0.0, 0.5 * math.sin((h - 7) / 11 * math.pi)) if 7 <= h <= 18 else 0.0
        out.append(planner.HourIn(t_out=t_out, wind=4, rad=rad, p_grid=p, p_own=0.05, own_kw=(own[i] if own else 0.0),
                                  day=7 <= h < 22, hour=h))
    return out


def test_cold_day_stores_heat_before_expensive_evening():
    s = planner.Settings()
    p = planner.plan(HOUSE, PUMP, s, hours(0), t_now=20.6, e_now=2.0, sp_now=20.5)
    midday = [h.sp for h in p.hours[2:8]]          # 10–16 h
    assert max(midday) > s.comfort, [h.sp for h in p.hours]
    assert p.cost < p.baseline_cost and p.saving > 0.2, (p.cost, p.baseline_cost, p.saving)
    assert p.min_day >= s.day_min - 0.05


def test_mild_day_does_nothing_special():
    p = planner.plan(HOUSE, PUMP, planner.Settings(), hours(12), t_now=21.0, e_now=0.0, sp_now=20.5)
    assert abs(p.cost - p.baseline_cost) < 0.15 and p.kwh < 4


def test_never_far_above_the_room_and_never_too_cold():
    s = planner.Settings()
    T = 19.6
    p = planner.plan(HOUSE, PUMP, s, hours(-3), t_now=T, e_now=0.0, sp_now=19.5)
    assert p.first.sp <= T + s.max_above_room + 1e-9 or p.first.sp <= s.day_min
    later = [h.t_end for h, x in zip(p.hours[3:], hours(-3)[3:]) if x.day]       # the floor needs an hour or two to respond
    assert min(later) >= s.day_min - 0.1, [round(h.t_end, 1) for h in p.hours]


def test_a_setpoint_set_too_far_above_the_room_comes_down():
    """21.5 was set with 'at most 1.5 above the room'; the user turns that back to 1.0 with the room at 20.1: keeping
    21.5 (the thermostat asking for 37 °C water) is no longer allowed."""
    s = planner.Settings(max_above_room=1.0)
    p = planner.plan(HOUSE, PUMP, s, hours(5), t_now=20.1, e_now=0.0, sp_now=21.5)
    assert p.first.sp <= 20.1 + s.max_above_room + planner.HOLD_MARGIN, [h.sp for h in p.hours[:4]]



def test_own_solar_is_used_for_storing():
    s = planner.Settings()
    own = [0, 0, 3, 3, 3, 3, 0, 0] + [0] * 16
    flat = [0.30] * 24
    p_sun = planner.plan(HOUSE, PUMP, s, hours(5, flat, own=own), t_now=20.6, e_now=1.0, sp_now=20.5)
    p_none = planner.plan(HOUSE, PUMP, s, hours(5, flat), t_now=20.6, e_now=1.0, sp_now=20.5)
    assert sum(h.kwh for h in p_sun.hours[2:6]) > sum(h.kwh for h in p_none.hours[2:6]) + 0.3


def test_store_max_equal_to_comfort_switches_storing_off():
    s = planner.Settings(store_max=20.5)
    p = planner.plan(HOUSE, PUMP, s, hours(0), t_now=20.6, e_now=2.0, sp_now=20.5)
    assert max(h.sp for h in p.hours) <= 20.5


def test_planner_is_fast_enough():
    t0 = time.time()
    planner.plan(HOUSE, PUMP, planner.Settings(), hours(0), t_now=20.6, e_now=2.0, sp_now=20.5)
    dt = time.time() - t0
    assert dt < 5.0, dt
    print(f"      (24 h plan in {dt:.2f} s)")


def test_replay_day_saving():
    s = planner.Settings()
    hs = hours(0)
    p = planner.plan(HOUSE, PUMP, s, hs, t_now=20.6, e_now=2.0, sp_now=20.5)
    entries = [{"T": 20.6 if i == 0 else 0, "E": 2.0, "sp": h.sp, "t_out": x.t_out, "rad": x.rad, "wind": x.wind, "p_grid": x.p_grid,
                "p_own": x.p_own, "own": x.own_kw, "day": x.day} for i, (h, x) in enumerate(zip(p.hours, hs))]
    roost, steady, bd = planner.replay_day(HOUSE, PUMP, s, entries)
    assert steady - roost > 0.2, (roost, steady)
    # the breakdown adds up to the same saving, hour by hour plus the state at the end
    assert len(bd["hours"]) == 24
    assert abs(sum(r["save"] for r in bd["hours"]) + bd["b_end"] - bd["end"] - bd["saving"]) < 0.01, bd
    assert abs(bd["saving"] - (steady - roost)) < 0.01, (bd["saving"], steady - roost)
    assert all(r["tariff"] is None for r in bd["hours"])        # hours logged before the tariff was kept


def test_lowest_setpoint_above_day_minimum():
    """A lowest setpoint above the day minimum (20 and 19.5) gave no setpoint at all for a cold room in the search
    (max_above_room ruled out every one): ValueError on every plan. The lowest setting is always allowed."""
    s = planner.Settings(comfort=20.5, day_min=19.5, night_min=19.0, sp_min=20.0, max_above_room=0.5)
    p = planner.plan(HOUSE, PUMP, s, hours(5), t_now=18.0, e_now=0.0, sp_now=20.0)
    assert p.first is not None and min(h.sp for h in p.hours) >= 20.0
    slow = heatpump.HeatPumpModel.from_dict({**PUMP.as_dict(), "follow": 0.3})      # also through polish()
    p = planner.plan(HOUSE, slow, s, hours(5), t_now=18.0, e_now=0.0, sp_now=20.0, w_now=0.0)
    assert p.first is not None and min(h.sp for h in p.hours) >= 20.0

def test_breakdown_shows_tariff_beside_price():
    """Issue #5: with a home battery the plan counts the price of buying a kWh back later, not the tariff; the
    breakdown (the look back report) keeps both, for the plan and for a replayed day."""
    s = planner.Settings()
    hs = [planner.replace(h, p_grid=0.416, p_own=0.416, p_imp=0.25 + 0.01 * i) for i, h in enumerate(hours(0))]
    p = planner.plan(HOUSE, PUMP, s, hs, t_now=20.6, e_now=2.0, sp_now=20.5)
    assert [r["tariff"] for r in p.breakdown["hours"]] == [round(h.p_imp, 4) for h in hs[:len(p.breakdown["hours"])]]
    assert all(r["price"] == 0.416 for r in p.breakdown["hours"])
    entries = [{"T": 20.6 if i == 0 else 0, "E": 2.0, "sp": h.sp, "t_out": x.t_out, "rad": x.rad, "wind": x.wind, "p_grid": x.p_grid,
                "p_own": x.p_own, "own": x.own_kw, "day": x.day, "p_imp": x.p_imp} for i, (h, x) in enumerate(zip(p.hours, hs))]
    _, _, bd = planner.replay_day(HOUSE, PUMP, s, entries)
    assert bd["hours"][3]["tariff"] == 0.28 and bd["hours"][3]["price"] == 0.416


def test_replay_ending_colder_is_no_saving():
    """Ending the day colder than the steady thermostat saves electricity today that is bought back tomorrow: the
    replay counts what the state at the end still costs, so turning down at the end is not a saving."""
    s = planner.Settings()
    hs = hours(5, prices=[0.25] * 24)
    steady = [round(planner.baseline_sp(s, PUMP, HOUSE, h) * 2) / 2 for h in hs]
    base = [{"T": 20.5 if i == 0 else 0, "E": 0.0, "sp": sp, "t_out": x.t_out, "rad": x.rad, "wind": x.wind, "p_grid": x.p_grid,
             "p_own": x.p_own, "own": 0.0, "day": x.day, "hour": x.hour} for i, (sp, x) in enumerate(zip(steady, hs))]
    cold_end = [{**e, "sp": 17.0} if i >= 20 else e for i, e in enumerate(base)]     # 04:00-08:00 the next night: down
    r0, b0, _ = planner.replay_day(HOUSE, PUMP, s, base)
    r1, b1, bd = planner.replay_day(HOUSE, PUMP, s, cold_end)
    assert sum(x["kwh"] for x in bd["hours"]) < sum(x["b_kwh"] for x in bd["hours"])     # less electricity today ...
    # ... and only the smaller heat loss of the colder hours counts (counting the end the other way round gave ~0.89)
    assert b1 - r1 < b0 - r0 + 0.15, (b0 - r0, b1 - r1)


def test_plan_breakdown_adds_up():
    p = planner.plan(HOUSE, PUMP, planner.Settings(), hours(0), t_now=20.6, e_now=2.0, sp_now=20.5)
    bd = p.breakdown
    assert len(bd["hours"]) == 24 and abs(bd["saving"] - p.saving) < 0.01, (bd["saving"], p.saving)
    assert abs(bd["cost"] - p.cost) < 0.01 and abs(bd["b_cost"] - p.baseline_cost) < 0.01
    assert abs(sum(r["save"] for r in bd["hours"]) + bd["b_end"] - bd["end"] - bd["saving"]) < 0.01
    parts = bd["parts"]          # the parts add up to the saving; the sunny hours are a part of 'less electricity'
    assert abs(parts["less_kwh"] + parts["cheaper_hours"] + parts["end"] - bd["saving"]) < 0.01, parts
    assert parts["cheaper_hours"] > 0.1, parts                     # a cold day with a dear evening: mostly timing
    assert any(r["sun"] for r in bd["hours"]) and not all(r["sun"] for r in bd["hours"])


def test_guessed_prices_are_set_to_the_mean_of_the_known():
    hs = hours(5, prices=[0.20] * 6 + [0.40] * 18)
    guess = [False] * 6 + [True] * 18
    n = planner.neutral_prices(hs, guess)
    assert [h.p_grid for h in n[:6]] == [0.20] * 6 and all(abs(h.p_grid - 0.20) < 1e-9 for h in n[6:])
    assert all(h.p_own == 0.05 for h in n)                        # own solar keeps its (lower) export value
    assert planner.neutral_prices(hs, [False] * 24) is None        # nothing guessed: nothing to do
    assert planner.neutral_prices(hs, [False] * 24 + [True] * 12) is None    # only guesses past 24 h
    n = planner.neutral_prices(hs, [True] * 24)                              # the current hour is never a guess
    assert n[0].p_grid == 0.20 and all(abs(h.p_grid - 0.20) < 1e-9 for h in n)
    flat = hours(5, prices=[0.30] * 24)                                      # a price sensor without forecast
    assert planner.neutral_prices(flat, [False] + [True] * 23) is None


def test_published_prefix_preserves_real_zero_and_negative_prices_and_stops_at_gaps():
    assert series.published_prefix([.3, 0., -.1, None, .8]) == [.3, 0., -.1]
    assert series.published_prefix([None, .3]) == []
    assert series.published_prefix([.3, float("nan"), .2]) == [.3]
    assert series.published_prefix([.3, float("inf")]) == [.3]


def test_a_guessed_expensive_morning_does_not_move_tonight():
    """Tomorrow's prices are not published yet and are filled with today's: a plan built on them may store heat
    tonight for a guessed expensive morning; with the guesses at the mean of what is known it does not."""
    s = planner.Settings()
    prices = [0.25] * 6 + [0.45] * 6 + [0.25] * 24          # from 20:00; 02:00-08:00 guessed dear
    hs = hours(0, prices=prices, start=20)
    guess = [False] * 4 + [True] * 32
    real = planner.plan(HOUSE, PUMP, s, hs, t_now=20.5, e_now=0.0, sp_now=20.5)
    calm = planner.plan(HOUSE, PUMP, s, planner.neutral_prices(hs, guess), t_now=20.5, e_now=0.0, sp_now=20.5)
    assert max(h.sp for h in calm.hours[:6]) <= max(h.sp for h in real.hours[:6])


# ---------------------------------------------------------------- control

CS = control.ControlSettings()
NOW = 1_800_000_000.0


def test_control_sends_once_and_waits():
    mem = control.ControlMemory()
    d = control.decide(NOW, 21.0, 20.5, 20.6, 20.0, mem, CS, True)
    assert d.setpoint == 21.0
    d = control.decide(NOW + 600, 20.0, 21.0, 20.8, 20.0, mem, CS, True)
    assert d.setpoint is None and "next change" in d.reason
    assert d.why.code == "wait" and d.why.args == {"min": 50}       # code + values for the card's own language
    d = control.decide(NOW + 3700, 20.0, 21.0, 20.8, 20.0, mem, CS, True)
    assert d.setpoint == 20.0


def test_control_tolerance_pause_and_urgent():
    mem = control.ControlMemory()
    assert control.decide(NOW, 20.6, 20.5, 20.6, 20.0, mem, CS, True).setpoint is None
    mem.pause_until = NOW + 3600
    assert control.decide(NOW, 22.0, 20.5, 20.6, 20.0, mem, CS, True).setpoint is None
    mem = control.ControlMemory(last_write=NOW - 60)
    d = control.decide(NOW, 20.5, 19.5, 19.4, 20.0, mem, CS, True)
    assert d.setpoint == 20.5 and "minimum" in d.reason and d.why.code == "urgent"


def test_control_shadow_keeps_virtual_setpoint():
    mem = control.ControlMemory()
    d = control.decide(NOW, 21.0, 20.5, 20.6, 20.0, mem, CS, False)
    assert d.setpoint == 21.0 and mem.virtual_sp == 21.0
    d = control.decide(NOW + 4000, 21.0, 20.5, 20.6, 20.0, mem, CS, False)
    assert d.setpoint is None                      # virtually already on 21


# ---------------------------------------------------------------- energy value for the planner

def test_battery_selling_is_not_solar():
    assert value.solar_export_now(grid_kw=-7.9, battery_kw=10.1, pv_kw=0.23) == 0.0
    assert abs(value.solar_export_now(grid_kw=-2.0, battery_kw=0.0, pv_kw=3.0) - 2.0) < 1e-9
    assert abs(value.solar_export_now(grid_kw=-2.0, battery_kw=0.5, pv_kw=3.0) - 1.5) < 1e-9
    assert abs(value.solar_export_now(grid_kw=2.0, battery_kw=None, pv_kw=None, import_positive=False) - 2.0) < 1e-9


def test_house_use_from_grid_and_solar():
    assert abs(value.house_use(grid_kw=0.5, pv_kw=2.0, battery_kw=None) - 2.5) < 1e-9          # buying and making
    assert abs(value.house_use(grid_kw=-1.5, pv_kw=2.0, battery_kw=None) - 0.5) < 1e-9         # exporting the rest
    assert abs(value.house_use(grid_kw=-1.0, pv_kw=3.0, battery_kw=-1.5) - 0.5) < 1e-9         # the battery charges
    assert abs(value.house_use(grid_kw=0.0, pv_kw=0.0, battery_kw=0.8) - 0.8) < 1e-9           # the battery supplies
    assert abs(value.house_use(grid_kw=1.5, pv_kw=2.0, battery_kw=None, import_positive=False) - 0.5) < 1e-9
    assert value.house_use(grid_kw=-3.0, pv_kw=1.0, battery_kw=None) == 0.0                     # never below zero


def test_planner_prices_split():
    inp = value.EnergyInputs(import_price=[0.30] * 4, export_price=[0.05] * 4, pv_kwh=[0, 3, 0, 0], load_kwh=[0.4] * 4)
    ev = value.compute(inp)
    pr = value.planner_prices(inp, ev)
    assert pr[1].own_kw > 2 and pr[1].p_own == 0.05 and pr[1].p_grid == 0.30
    assert pr[0].own_kw == 0 and pr[0].p_grid == 0.30



def test_price_gaps_filled_with_the_day_before():
    # forecast until midnight (3 hours known), tomorrow's prices not published yet
    start = 1_800_000_000 - 1_800_000_000 % 3600
    vals = [0.25, 0.46, 0.37, None, None, None]
    seen = {start + 3 * 3600 - 86400: 0.22, start + 5 * 3600 - 2 * 86400: 0.20}
    out, guess = series.fill_gaps(vals, start, seen)
    assert out == [0.25, 0.46, 0.37, 0.22, 0.37, 0.20]   # a day earlier, nothing known (last value), two days earlier
    assert guess == [False, False, False, True, True, True]


def test_slots_from_state_changes():
    sl = series.slots_from_changes([(7200, 0.3), (0, 0.2)], 10800)
    assert sl == [(0, 7200, 0.2), (7200, 10800, 0.3)]
    assert series.hourly(sl, 0, 3, fill_last=False) == [0.2, 0.2, 0.3]



def test_zonneplan_prices():
    """Zonneplan keeps its forecast in 1e-7 euro while the sensor's state is in euro per kWh; per hour with
    'datetime'/'electricity_price', per quarter with 'start_date'/'end_date' and 'price_tax_included': {'amount': …}."""
    series = load("series")
    t0 = 1_800_000_000 - 1_800_000_000 % 3600
    iso = lambda t: __import__("datetime").datetime.fromtimestamp(t, __import__("datetime").timezone.utc).isoformat()
    hourly_attr = {"forecast": [{"datetime": iso(t0 + h * 3600), "electricity_price": 2_000_000 + h * 100_000,
                                 "electricity_price_excl_tax": 1_500_000, "tariff_group": "normal"} for h in range(24)]}
    slots = series.find_slots(hourly_attr)
    assert len(slots) == 24
    f = series.slot_scale(slots, "€/kWh", 0.2, t0 + 600)                    # the state: 0.20 €/kWh now
    assert abs(f - 1e-7) < 1e-12
    assert abs(series.hourly(slots, t0, 3)[2] * f - 0.22) < 1e-9
    assert abs(series.slot_scale(slots, "€/kWh", 0.002, t0 + 600) - 1e-7) < 1e-12   # price near zero now: by size
    quarter_attr = {"forecast": [{"start_date": iso(t0 + q * 900), "end_date": iso(t0 + (q + 1) * 900),
                                  "price_tax_included": {"amount": 2_000_000 + q * 10_000}} for q in range(8)]}
    qs = series.find_slots(quarter_attr)
    assert len(qs) == 8 and abs(series.hourly(qs, t0, 2)[0] * 1e-7 - 0.2015) < 1e-9          # the hour's average
    nordpool = series.find_slots({"raw_today": [{"start": iso(t0 + h * 3600), "end": iso(t0 + (h + 1) * 3600), "value": 0.25} for h in range(3)]})
    assert series.slot_scale(nordpool, "EUR/kWh", 0.25, t0) == 1.0                          # an ordinary sensor


def test_fixed_contract_prices():
    hours = [(0, 22), (0, 23), (1, 3), (1, 7), (5, 12), (6, 18)]       # Monday 22/23 h, Tuesday 3/7 h, Saturday, Sunday
    assert value.fixed_prices(hours, 0.30, 0.25) == [0.30, 0.25, 0.25, 0.30, 0.25, 0.25]
    assert value.fixed_prices(hours, 0.30, 0.25, low_weekend=False) == [0.30, 0.25, 0.25, 0.30, 0.30, 0.30]
    assert value.fixed_prices(hours, 0.30, 0.25, low_from=1, low_to=6, low_weekend=False) == [0.30, 0.30, 0.25, 0.30, 0.30, 0.30]
    assert value.fixed_prices(hours, 0.28) == [0.28] * 6               # single rate



def test_reasons_follow_the_heat_emitter():
    s = planner.Settings(comfort=20.5)
    hours = [planner.HourIn(t_out=2.0, wind=3.5, rad=0.0, p_grid=0.50 if i < 3 else 0.25, p_own=0.25) for i in range(12)]
    p = planner.Plan([planner.HourPlan(19.0, 20.6, 0.1, 0.4, 0.05, 0.5 if i < 3 else 0.25) for i in range(12)], 0, 0, 0, 0, 0, None)
    assert planner.explain(p, hours, 20.8, s).code == "expensive"
    assert planner.explain(p, hours, 20.8, s, floor=False).code == "expensive_house"



def test_a_warm_room_is_not_storing():
    """Evening, battery power counts as own, the room at 24.3 °C and the thermostat at 21: no heat goes in, so the
    reason is 'warm enough', not 'charging the floor'."""
    s = planner.Settings(comfort=20.5)
    hours = [planner.HourIn(t_out=14.0, wind=3.5, rad=0.0, p_grid=0.34, p_own=0.30, own_kw=2.0) for _ in range(12)]
    p = planner.Plan([planner.HourPlan(21.0, 23.5, 0.0, 0.0, 0.0, 0.34)], 0, 0, 0, 0, 0, None)
    r = planner.explain(p, hours, 24.3, s)
    assert r.code == "warm_enough" and r.args["room"] == 24.3, r
    p = planner.Plan([planner.HourPlan(21.0, 20.9, 0.6, 2.4, 0.1, 0.34)], 0, 0, 0, 0, 0, None)
    assert planner.explain(p, hours, 20.4, s).code == "store_solar"          # heat going in: it is storing

def test_every_hour_has_its_reason():
    """Issue #1: a reason per hour of the plan, each from the room expected at its start; cheap and dear on the price
    the planner counts (18-10: 'charging at 45.7 ct' while the battery supplied at 29 ct)."""
    s = planner.Settings(comfort=20.0)
    hours = [planner.HourIn(t_out=8.0, wind=3.5, rad=0.0, p_grid=0.457 if i == 0 else 0.33, p_own=0.29 if i == 0 else 0.33)
             for i in range(12)]
    hp = [planner.HourPlan(21.0, 20.2, 0.5, 2.0, 0.15, 0.29)] + [planner.HourPlan(20.0, 20.1, 0.2, 0.8, 0.07, 0.33)] * 10 + \
         [planner.HourPlan(19.0, 21.4, 0.0, 0.0, 0.0, 0.33)]
    p = planner.Plan(hp, 0, 0, 0, 0, 0, None)
    why = planner.explain_hours(p, hours, 20.4, s)
    assert len(why) == 12
    assert why[0].code == "store_cheap" and why[0].args["ct"] == 29.0, why[0]      # the price it counted, not the tariff
    assert why[0] == planner.explain(p, hours, 20.4, s)                           # hour 0 is the reason shown on top
    assert why[1].code == "holding"
    assert why[11].code == "warm_enough" and why[11].args["room"] == 20.1          # the room expected at its start


def test_away_keeps_only_the_minimum_and_is_warm_again_on_time():
    """Away for the whole horizon: far less heat, never below the away minimum. Back after 20 hours (07:00): the room is
    at the day minimum again by then (a slow house is kept warm rather than reheated in an expensive morning)."""
    import dataclasses
    s = planner.Settings(comfort=20.5, day_min=20.0, night_min=19.0, away_min=16.0, sp_min=15.0)
    home = hours(-3)
    p_home = planner.plan(HOUSE, PUMP, s, home, t_now=20.6, e_now=1.0, sp_now=20.5)
    p_away = planner.plan(HOUSE, PUMP, s, [dataclasses.replace(h, away=True) for h in home], t_now=20.6, e_now=1.0, sp_now=20.5)
    assert sum(h.kwh for h in p_away.hours) < 0.2 * sum(h.kwh for h in p_home.hours)
    assert min(h.t_end for h in p_away.hours) >= 16.0 - 0.3
    p_back = planner.plan(HOUSE, PUMP, s, [dataclasses.replace(h, away=i < 20) for i, h in enumerate(home)], t_now=20.6, e_now=1.0, sp_now=20.5)
    assert p_back.hours[22].t_end >= 19.8, [round(h.t_end, 1) for h in p_back.hours]


def test_unknown_thermostat_starts_low_not_in_the_middle():
    """Just after a start the thermostat may be unavailable: on a warm afternoon the plan then keeps the lowest
    setting, not an arbitrary middle one (seen 20-10: 19 -> 22 -> 19 after each restart, with no heat either way)."""
    s = planner.Settings(comfort=20.0, day_min=19.0, night_min=19.0, sp_min=19.0, store_max=25.0)
    warm = hours(13)
    p = planner.plan(HOUSE, PUMP, s, warm, t_now=23.0, e_now=0.0, sp_now=None)
    assert p.first.sp == 19.0, [h.sp for h in p.hours[:6]]
    p = planner.plan(HOUSE, PUMP, s, warm, t_now=23.0, e_now=0.0, sp_now=19.0)
    assert p.first.sp == 19.0                                                     # and stays where it is


def test_heating_ahead_of_dearer_hours_says_so():
    """21-10: the floor kept warm at night at the battery's 37.5 ct for a dear morning said 'keeping the room at
    temperature'; it names the dearer hours now."""
    s = planner.Settings(comfort=20.0)
    hs = [planner.HourIn(t_out=10.0, wind=3.5, rad=0.0, p_grid=0.375, p_own=0.375, day=False, hour=(21 + k) % 24) for k in range(4)] + \
         [planner.HourIn(t_out=9.0, wind=3.5, rad=0.0, p_grid=0.30, p_own=0.30, day=False, hour=1 + k) for k in range(6)] + \
         [planner.HourIn(t_out=9.0, wind=3.5, rad=0.0, p_grid=0.43, p_own=0.43, day=True, hour=7 + k) for k in range(2)]
    p = planner.Plan([planner.HourPlan(21.0, 20.4, 0.3, 1.0, 0.11, h.p_grid) for h in hs[:10]] +
                     [planner.HourPlan(19.0, 20.4, 0.1, 0.3, 0.04, h.p_grid) for h in hs[10:]], 0, 0, 0, 0, 0, None)
    r = planner.explain(p, hs, 20.3, s, PUMP, HOUSE, True, 0)      # 37.5 ct is not cheap here: 30 ct follows
    assert r.code == "store_ahead" and r.args == {"ct": 43.0, "at": 7}, r
    assert str(r) == "warming the floor ahead of dearer hours (43 ct from 7:00)"
    assert planner.explain(p, hs, 20.3, s, PUMP, HOUSE, True, 4).code == "store_cheap"           # 30 ct: cheap


def test_one_fixed_rate_has_no_cheap_or_dear_hours():
    """#4: with one fixed rate no hour is 'cheap' or 'expensive' (every hour was both before)."""
    s = planner.Settings(comfort=20.0)
    flat = [planner.HourIn(t_out=9.0, wind=3.5, rad=0.0, p_grid=0.23, p_own=0.23) for _ in range(12)]
    p = planner.Plan([planner.HourPlan(21.0, 20.4, 0.5, 2.0, 0.1, 0.23)] + [planner.HourPlan(20.0, 20.3, 0.2, 0.8, 0.05, 0.23)] * 11,
                     0, 0, 0, 0, 0, None)
    assert planner.explain(p, flat, 20.2, s).code not in ("store_cheap", "store_cheap_house", "expensive", "expensive_house")


def test_fast_house_with_a_fixed_rate_does_not_preheat():
    """#4 (the model numbers of the report): radiators, learned lag 0.29 h, one fixed rate. Nothing to gain by heating
    earlier, but the search dropped the heat still on its way to the room and planned 21 °C all evening."""
    house = model.HouseModel(C=9.0, H=0.123, g=7.4, lag=0.29, internal=0.19, Hw=0.0074, source="learned")
    pump = heatpump.HeatPumpModel.for_profile("p80")
    for k, v in dict(a=1.2, k=1.5, offset=-0.1, follow=0.7, th_diff=0.07).items():
        setattr(pump, k, v)
    s = planner.Settings(comfort=20.0, day_min=20.0, night_min=20.0, sp_min=20.0, store_max=22.0)
    flat = [planner.HourIn(t_out=max(5.0, 9.2 - 0.5 * i) if i < 12 else 5.0 + 0.4 * (i - 12), wind=3.5, rad=0.0, p_grid=0.232,
                           p_own=0.232, day=7 <= (19 + i) % 24 < 22, hour=(19 + i) % 24) for i in range(36)]
    p = planner.plan(house, pump, s, flat, t_now=20.22, e_now=0.0, sp_now=20.0, w_now=0.0)
    assert max(h.sp for h in p.hours[:12]) <= 20.5, [h.sp for h in p.hours[:12]]


def test_heat_pump_power_by_source():
    """In the same mix as the house: solar first, then the battery, the rest from the grid."""
    sun, bat, grid = value.source_split(hp_kw=2.0, house_kw=2.5, pv_kw=1.0, battery_kw=0.5)
    assert (round(sun, 3), round(bat, 3), round(grid, 3)) == (0.8, 0.4, 0.8)
    assert value.source_split(2.0, 2.5, 4.0, 0.0) == (2.0, 0.0, 0.0)             # plenty of solar: all solar
    assert value.source_split(0.0, 0.5, 1.0, 0.0) == (0.0, 0.0, 0.0)


if __name__ == "__main__":
    run_all(dict(globals()))
