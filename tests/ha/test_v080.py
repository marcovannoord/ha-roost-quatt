"""v0.8.0 in Home Assistant: the plan held, fallbacks, airing with a window sensor, the unit's minimum run, a house that
stays cold, and the fixes from the 0.7.8 review (R01, R04, R07, R08, R10, R16, R17, R21, R22)."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from custom_components.roost_quatt import diagnostics, rooms, schedule, stick
from custom_components.roost_quatt.sensor import SavingMonthSensor

from .conftest import THERMOSTAT, thermostat


@pytest.fixture(autouse=True)
def mutable_test_configuration(entry, monkeypatch):
    m = entry.runtime_data
    conf = m.conf
    monkeypatch.setattr(type(m), "conf", property(lambda _self: conf))


def issue(hass, entry, key):
    return ir.async_get(hass).async_get_issue("roost_quatt", f"{entry.entry_id}_{key}")


async def test_the_plan_is_held_until_a_reason(hass, entry):
    m = entry.runtime_data
    now = dt_util.utcnow().replace(minute=5, second=0, microsecond=0)    # +20 min stays in the same hour
    await m._async_plan(now, "first")
    held = list(m.commit.sp)
    m.storage_e += 1.5                                   # a small change: the plan made afresh might differ
    await m._async_plan(now + timedelta(minutes=20))
    assert [x.sp for x in m.plan.hours] == held[:len(m.plan.hours)] and m.plan_why == "first"
    await m._async_plan(now + timedelta(minutes=40), "settings")
    assert m.plan_why == "settings" and m.commit.at == pytest.approx((now + timedelta(minutes=40)).timestamp())


async def test_why_plan_sees_new_prices(hass, entry):
    m = entry.runtime_data
    now = dt_util.utcnow()
    await m._async_plan(now, "first")
    e = m._energy(now, 36)
    assert m._why_plan(now, e, None) is None
    short = (type(e[0])(import_price=e[0].import_price[:10]), e[1])
    m.commit.tariff = m.commit.tariff[:10]
    assert m._why_plan(now, e, None) == "prices"
    assert m._why_plan(now, short, None) is None


async def test_no_room_falls_back_to_the_comfort_schedule(hass, entry):
    m = entry.runtime_data
    now = dt_util.utcnow()
    with patch.object(type(m), "room", return_value=None):
        await m._async_plan(now)
        assert m.fallback is None and m.reason.code == "no_room"
        later = now + timedelta(minutes=61)
        await m._async_plan(later)
        assert m.fallback == "schedule" and m.plan is None
        assert m.planned_sp(later.timestamp()) == m.fallback_sp(later.timestamp())
        await m._async_plan(now + timedelta(hours=3, minutes=5))
        assert issue(hass, entry, "fallback") is not None
    await m._async_plan(now + timedelta(hours=3, minutes=10))
    assert m.fallback is None and issue(hass, entry, "fallback") is None


async def test_a_failed_write_is_tried_again_soon(hass, entry):
    """R01: the change interval only starts with a change that was made."""
    m = entry.runtime_data
    thermostat(hass, target=19.0, room=20.0)
    await hass.async_block_till_done()
    m.mode = "active"
    t = dt_util.utcnow().timestamp()

    async def boom(call):
        raise RuntimeError("timeout")
    hass.services.async_register("climate", "set_temperature", boom)
    with patch.object(type(m), "planned_sp", return_value=21.0):
        await m._async_control(t)
        assert m.decision.why.code == "set_failed" and m.decision.effective == 19.0
        await m._async_control(t + 60)
        assert m.decision.why.code == "wait" and m.decision.why.args["min"] <= 4
        await m._async_control(t + 5 * 60 + 1)
        assert m.decision.why.code == "set_failed" and m.decision.why.args["min"] == 10     # backs off


async def test_the_unit_runs_a_while_before_roost_lowers(hass, entry, climate_calls):
    m = entry.runtime_data
    thermostat(hass, target=21.5, room=20.9)
    await hass.async_block_till_done()
    m.mode = "active"
    t = dt_util.utcnow().timestamp()
    m._heating_since = t - 10 * 60
    with patch.object(type(m), "planned_sp", return_value=20.0):
        await m._async_control(t)
        assert m.decision.why.code == "min_run" and not climate_calls
        m._heating_since = t - 45 * 60
        m.mem.last_write = None
        await m._async_control(t)
        assert climate_calls and climate_calls[-1].data["temperature"] == 20.0


async def test_a_window_sensor_lowers_the_thermostat_and_closing_restores_the_plan(hass, entry, climate_calls):
    """R13: with a contact the unit stops heating the outdoors; a fall of the room alone only pauses."""
    m = entry.runtime_data
    m.conf["window_sensors"] = ["binary_sensor.window"]
    m.conf["lowest_setpoint"] = 19.0
    thermostat(hass, target=22.0, room=21.0)
    await hass.async_block_till_done()
    m.mode = "active"
    hass.states.async_set("binary_sensor.window", "on")
    t = dt_util.utcnow().timestamp()
    m._watch_window(t)
    await m._async_control(t)
    assert climate_calls[-1].data["temperature"] == 19.0 and m.decision.why.code == "airing"
    n = len(climate_calls)
    m.mode = "shadow"
    thermostat(hass, target=19.0, room=20.5)
    await hass.async_block_till_done()
    m.mode = "active"
    await m._async_control(t + 120)
    assert len(climate_calls) == n                       # once
    hass.states.async_set("binary_sensor.window", "off")
    with patch.object(type(m), "_async_tick") as tick:
        for k in range(1, 4):
            m._watch_window(t + k * 3600)
        assert tick.call_args.kwargs.get("force_plan") == "window"
    assert m._airing_from is None and m.mem.last_write is None


async def test_a_house_below_its_minimum_gets_a_notice(hass, entry):
    m = entry.runtime_data
    m.mode = "active"
    t = dt_util.utcnow().timestamp()
    with patch.object(type(m), "room", return_value=17.5):
        m._check_health(t)
        assert issue(hass, entry, "house_cold") is None
        m._check_health(t + 61 * 60)
        assert issue(hass, entry, "house_cold") is not None
    m._check_health(t + 62 * 60)
    assert issue(hass, entry, "house_cold") is None


def _heating(hass, m, watts) -> None:
    """The CIC heating with the units taking `watts` (a Quatt has no energy meter: Roost integrates the power)."""
    hass.states.async_set(m.ent["state"], "2")
    hass.states.async_set(m.ent["power_in"], str(watts) if watts is not None else "unavailable",
                          {"device_class": "power", "unit_of_measurement": "W"})


async def test_a_missing_meter_makes_no_phantom_use(hass, entry):
    """R16 for a Quatt: the power reading unavailable for a while adds nothing, and its return adds only the time since
    the last run (not the gap)."""
    m = entry.runtime_data
    now = dt_util.utcnow()
    t = now.timestamp()
    _heating(hass, m, None)
    m._last_tick = t - 120
    before = m.kwh_today
    m._count_cost(now)
    assert m.kwh_today == before
    _heating(hass, m, 1200)
    m._last_tick = t + 3600 - 120                     # an hour later, two minutes after the last run
    m._count_cost(now + timedelta(hours=1))
    assert m.kwh_today - before == pytest.approx(1.2 * 120 / 3600)


async def test_energy_without_a_plan_is_priced_or_marked_unpriced(hass, entry):
    """R17: not free."""
    m = entry.runtime_data
    now = dt_util.utcnow()
    t = now.timestamp()
    m.plan, m.plan_hours, m.plan_at = None, [], None
    _heating(hass, m, 3000)                           # 3 kW for 20 minutes: 1 kWh
    m._tariff_now = 0.30
    m._last_tick = t - 600                            # at most 10 minutes per run count: two runs of 10 minutes
    m._count_cost(now)
    m._last_tick = t
    m._count_cost(now + timedelta(minutes=10))
    assert m.cost_today == pytest.approx(0.30)
    m._tariff_now = None
    for k in (2, 3):
        m._last_tick = t + (k - 1) * 600
        m._count_cost(now + timedelta(minutes=10 * k))
    assert m.cost_today == pytest.approx(0.30) and m.unpriced_kwh == pytest.approx(1.0)


async def test_standby_is_not_heating_electricity(hass, entry):
    """A Quatt standing still takes ~10 W: not counted as heating, as a heat pump's own meter for heating does."""
    m = entry.runtime_data
    now = dt_util.utcnow()
    hass.states.async_set(m.ent["state"], "0")
    hass.states.async_set(m.ent["power_in"], "12", {"device_class": "power", "unit_of_measurement": "W"})
    m._last_tick = now.timestamp() - 120
    before = m.kwh_today
    m._count_cost(now)
    assert m.kwh_today == before


async def test_a_change_undone_within_the_hour_still_marks_the_day(hass, entry):
    """R04."""
    m = entry.runtime_data
    now = dt_util.utcnow()
    day = dt_util.as_local(now).date().isoformat()
    m.day_contexts[day] = {"settings": vars(m.settings()), "room_settings": [], "comfort_schedule": schedule.context(m.conf)}
    m.hour_log.append({"ts": int(now.timestamp() // 3600 * 3600)})      # this hour is logged already
    m._log_hour(now)
    assert not m.day_contexts[day].get("settings_changed")
    old = m.conf["comfort"]
    m.conf["comfort"] = old + 1
    m._log_hour(now + timedelta(seconds=30))
    m.conf["comfort"] = old
    m._log_hour(now + timedelta(seconds=60))
    assert m.day_contexts[day]["settings_changed"]


async def test_failed_learning_keeps_the_models_it_had(hass, entry):
    """R21."""
    m = entry.runtime_data
    house, pump, chk = m.house, m.pump, m.check
    with patch("custom_components.roost_quatt.check.self_check", side_effect=RuntimeError("boom")), \
         patch("custom_components.roost_quatt.learning.async_rows", return_value=([], {})), \
         patch("custom_components.roost_quatt.model.stale", return_value=False), \
         patch("custom_components.roost_quatt.model.learn") as learn, \
         patch("custom_components.roost_quatt.heatpump.learn", side_effect=lambda rows, p: (p, "")), \
         patch("custom_components.roost_quatt.response.learn", side_effect=lambda rows, h, p: (p, "")), \
         patch.object(type(m), "_async_tick"):
        learn.return_value.model = type(house)(C=40.0)
        await m.async_learn()
    assert m.house is house and m.pump is pump and m.check == chk


async def test_month_coverage_counts_absent_days(hass, entry):
    """R22."""
    m = entry.runtime_data
    today = dt_util.now().date()
    if today.day < 3:
        pytest.skip("needs two completed days in this month")
    first = today.replace(day=1).isoformat()
    m.day_stats = {first: {"saving": 0.1}}
    m.saving_days = {first: 0.1}
    a = SavingMonthSensor(m).extra_state_attributes
    assert a["partial"] and len(a["absent_days"]) == today.day - 2 and a["days_expected"] == today.day - 1


async def test_inherited_room_follows_the_weekly_schedule(hass, entry):
    """R07: a room of kind 'other' without its own hours keeps the house's comfort hours, also weekly ones."""
    m = entry.runtime_data
    m.rooms = [rooms.Room(id="r1", name="Upstairs", sensor="sensor.upstairs", kind="other")]
    hass.states.async_set("sensor.upstairs", "19.0", {"unit_of_measurement": "°C"})
    m.conf.update({schedule.ENABLED: True, schedule.WEEK: schedule.normalise({})})
    now = dt_util.utcnow()
    hours = m._hours_ahead(now, [type("P", (), {"p_grid": .3, "p_own": .3, "own_kw": 0.0})()] * 3, [.3] * 3)
    plan_in, meta = m._rooms_ahead(hours)
    assert plan_in[0]["active"] == [False, False, False]


async def test_an_unread_room_stays_in_the_status(hass, entry):
    """R08."""
    m = entry.runtime_data
    m.rooms = [rooms.Room(id="r1", name="Upstairs", sensor="sensor.upstairs", kind="bedroom")]
    hass.states.async_set("sensor.upstairs", "unavailable")
    plan_in, meta = m._rooms_ahead([])
    assert plan_in == [] and meta[0]["available"] is False and meta[0]["temperature"] is None


def test_diagnostics_scrub_the_location_from_text():
    """R10."""
    text = {"sources": {"weather": "Open-Meteo unavailable: 500, url=https://x/?latitude=52.0912&longitude=5.1214&hourly=t"},
            "log": ["at 52.0912, 5.1214 it failed"]}
    out = diagnostics._scrub(text, ("52.0912", "5.1214"))
    assert "52.0912" not in str(out) and "5.1214" not in str(out) and "hourly=t" in str(out)


async def test_the_card_saves_weekly_periods_without_a_reload(hass, entry):
    """The weekly periods from the card: checked like Configure > Comfort, no reload of Roost."""
    from homeassistant.exceptions import ServiceValidationError
    m = entry.runtime_data
    week = {"monday": [[420, 540], [1050, 1320]], "sunday": "08:30-23:00"}
    with patch.object(type(m), "_async_tick"):
        await hass.services.async_call("roost_quatt", "set_settings", {"weekly_comfort": True, "comfort_schedule": week}, blocking=True)
    await hass.async_block_till_done()
    assert entry.runtime_data is m                                   # not reloaded
    assert entry.options[schedule.ENABLED] is True
    assert entry.options[schedule.WEEK]["monday"] == [[420, 540], [1050, 1320]] and entry.options[schedule.WEEK]["tuesday"] == []
    m.conf.update(entry.options)                                     # the test's fixed conf: as Home Assistant merges it
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("roost_quatt", "set_settings", {"comfort_schedule": {"monday": [[420, 600], [540, 700]]}}, blocking=True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("roost_quatt", "set_settings", {"day_from": 6}, blocking=True)
    with patch.object(type(m), "_async_tick"):
        await hass.services.async_call("roost_quatt", "set_settings", {"weekly_comfort": False}, blocking=True)
    assert entry.options[schedule.ENABLED] is False and entry.options[schedule.WEEK]["monday"] == [[420, 540], [1050, 1320]]


async def test_weekly_on_without_periods_starts_from_the_comfort_hours(hass, entry):
    m = entry.runtime_data
    m.conf.pop(schedule.WEEK, None)
    with patch.object(type(m), "_async_tick"):
        await m.async_set_settings(weekly_comfort=True)
    assert entry.options[schedule.WEEK]["friday"] == [[int(m.conf["day_from"]) * 60, int(m.conf["day_to"]) * 60]]


async def test_runs_of_the_unit_are_counted_per_day(hass, entry):
    m = entry.runtime_data
    t = dt_util.utcnow().timestamp()
    m.runs = []
    m._track_runs(t - 3600, True)
    m._track_runs(t - 1800, False)
    m._track_runs(t - 600, True)
    s = m.run_stats(t)
    assert s["heating"] and s["today"]["starts"] in (1, 2)
    if s["today"]["starts"] == 2:                                    # not just after midnight
        assert s["today"]["minutes"] == round((30 + 10) / 2)


async def test_an_install_from_v077_starts_and_drops_unchecked_savings(hass, quatt, climate_calls, hass_storage):
    """Upgrading from v0.1.0 (Roost v0.7.7): its stored state has none of the new fields (frozen day contexts, the plan held, the
    unit's runs, saving quality). Roost starts, steers, and no longer counts the old unchecked days in the month."""
    from homeassistant.setup import async_setup_component
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.roost_quatt.const import STORAGE_VERSION
    from .conftest import PRICE
    assert await async_setup_component(hass, "websocket_api", {})
    day = (dt_util.now() - timedelta(days=2)).date().isoformat()
    hass_storage["roost_quatt.old077"] = {"version": STORAGE_VERSION, "key": "roost_quatt.old077", "data": {
        "mode": "active", "saving_days": {day: 0.42}, "day_stats": {day: {"saving": 0.42, "kwh": 3.1}},
        "saving_detail": {day: {"saving": 0.42}}, "replayed_with": 2, "hour_log": [], "plan_log": [],
        "control": {"last_write": None, "last_sp": 20.5}, "storage_e": 1.2, "today": {"day": day, "cost": 0.5, "kwh": 2.0}}}
    entry = MockConfigEntry(domain="roost_quatt", entry_id="old077", title="Roost", unique_id=quatt,
                            data={"heat_pump": quatt, "thermostat": THERMOSTAT, "import_price": PRICE,
                                  "import_history": False, "weather_source": "open_meteo"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    m = entry.runtime_data
    assert m.mode == "active" and m.commit is not None and m.plan is not None and isinstance(m.runs, list)   # it planned at once
    assert day not in m.saving_days and m.saving_month() is None
    assert m.day_stats[day]["quality"]["reasons"] == ["missing_context"]
