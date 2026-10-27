"""Setting up, a first plan, shadow and active mode, a manual change, diagnostics."""
from __future__ import annotations

import time

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Context, HomeAssistant

from custom_components.roost_quatt.diagnostics import async_get_config_entry_diagnostics

from .conftest import THERMOSTAT, setup_roost, thermostat


def _plan_entity(hass: HomeAssistant) -> str:
    return next(s.entity_id for s in hass.states.async_all("sensor") if s.entity_id.endswith("planned_setpoint"))


async def test_setup_finds_the_quatt_sensors_and_plans(hass: HomeAssistant, entry) -> None:
    assert entry.state is ConfigEntryState.LOADED
    m = entry.runtime_data
    assert {"state", "power_out", "power_in", "outdoor", "water_setpoint", "water_out", "power_in_hp2"} <= set(m.ent)
    assert m.pump_name == "Quatt Duo" and m.pump.source.startswith("profile quatt_duo")
    assert m.ent["water_out"].endswith("heatpump_2_hp2_temperaturewaterout")      # the Duo's second unit feeds the house
    st = hass.states.get(_plan_entity(hass))
    assert st is not None and st.state not in ("unknown", "unavailable")
    assert len(st.attributes["plan"]) == 24
    assert hass.states.get("select.roost_mode").state == "shadow"


async def test_shadow_mode_never_touches_the_thermostat(hass: HomeAssistant, entry, climate_calls) -> None:
    m = entry.runtime_data
    await m._async_tick(None, force_plan=True)
    assert climate_calls == []


async def test_active_mode_sets_the_thermostat(hass: HomeAssistant, entry, climate_calls) -> None:
    m = entry.runtime_data
    thermostat(hass, target=18.0, room=20.6)            # far from any plan
    await m.async_set_mode("active")
    await hass.async_block_till_done()
    assert climate_calls, "no thermostat command in active mode"
    assert climate_calls[-1].data["entity_id"] == THERMOSTAT
    sent = len(climate_calls)
    await m._async_tick(None)
    assert len(climate_calls) == sent                   # at most one change per hour


async def test_manual_change_pauses(hass: HomeAssistant, entry, climate_calls) -> None:
    m = entry.runtime_data
    await m.async_set_mode("active")
    m.mem.last_write = time.time() - 3600
    hass.states.async_set(THERMOSTAT, "heat", {"temperature": 22.0, "current_temperature": 20.6}, context=Context())
    await hass.async_block_till_done()
    assert m.mem.pause_until and m.mem.pause_until > time.time()
    assert hass.states.get("binary_sensor.roost_paused_changed_by_hand").state == "on"


async def test_diagnostics_and_unload(hass: HomeAssistant, entry) -> None:
    d = await async_get_config_entry_diagnostics(hass, entry)
    assert d["mode"] == "shadow" and d["plan"] and d["quatt_entities"]
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_the_plan_inputs_are_kept_for_a_replay(hass: HomeAssistant, entry) -> None:
    """Each hour the plan in force is kept with all it saw, so a decision can be replayed from the diagnostics."""
    m = entry.runtime_data
    assert m.plan and m.plan_hours
    m._log_plan(int(time.time() // 3600 * 3600), 20.3)
    d = await async_get_config_entry_diagnostics(hass, entry)
    snap = d["plan_log"][-1]
    assert snap["room"] == 20.3 and len(snap["hours"]) == len(m.plan_hours) and len(snap["hours"][0]) == 9
    assert snap["sp"] == [h.sp for h in m.plan.hours]


async def test_no_login_is_asked(hass: HomeAssistant, entry) -> None:
    """Roost for Quatt reads the Quatt integration's entities: no re-authenticate notice."""
    assert not hass.config_entries.flow.async_progress_by_handler("roost_quatt")


async def test_built_in_day_ahead_prices(hass: HomeAssistant, quatt: str, aioclient_mock, climate_calls) -> None:
    """Price mode 'epex': Roost fetches the day-ahead prices itself and plans with day-ahead × multiplier + amount."""
    from homeassistant.setup import async_setup_component
    from homeassistant.util import dt as dt_util

    from custom_components.roost_quatt import epex

    from .conftest import setup_roost

    t0 = int(dt_util.utcnow().timestamp() // 3600 * 3600) - 3600
    quarters = list(range(0, 48 * 4))
    aioclient_mock.get(epex.URL, json={"unix_seconds": [t0 + q * 900 for q in quarters],
                                       "price": [100.0 if (q // 4) % 2 else 300.0 for q in quarters], "unit": "EUR / MWh"})
    assert await async_setup_component(hass, "websocket_api", {})
    entry = await setup_roost(hass, quatt, options={"price_mode": "epex", "epex_zone": "NL", "import_mult": 1.21,
                                                     "import_add": 0.15})
    m = entry.runtime_data
    assert aioclient_mock.call_count == 1 and m.sources.get("epex") == "ok"
    assert m.sources.get("price") == "epex"
    tariff = [round(x, 4) for x in m.plan_tariff[:4]]
    assert set(tariff[1:]) <= {round(0.1 * 1.21 + 0.15, 4), round(0.3 * 1.21 + 0.15, 4)}, tariff


async def test_look_back_over_the_websocket(hass: HomeAssistant, entry) -> None:
    """The card's look back: roost/history for the planned-setpoint entity gives the hours, events and days. (The
    handler is called with a stand-in connection: the web server is a mock in these tests.)"""
    from custom_components.roost_quatt import _ws_history

    class Conn:
        def __init__(self) -> None:
            self.result, self.error = None, None

        def send_result(self, msg_id, result) -> None:
            self.result = result

        def send_error(self, msg_id, code, message) -> None:
            self.error = code

        def async_handle_exception(self, msg, err) -> None:
            raise err

    m = entry.runtime_data
    m.hour_log.append({"ts": int(time.time() // 3600 * 3600) - 3600, "T": 20.4, "sp_t": 20.5, "sp_plan": 20.5, "p6": 20.6,
                       "reason": "holding", "args": {}, "p_grid": 0.3, "q": 1.2, "day": True})
    ok = Conn()
    _ws_history(hass, ok, {"id": 1, "type": "roost/history", "entity_id": _plan_entity(hass), "days": 2})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert ok.result and ok.result["hours"][-1]["p6"] == 20.6 and "events" in ok.result and "days" in ok.result
    bad = Conn()
    _ws_history(hass, bad, {"id": 2, "type": "roost/history", "entity_id": "sensor.not_roost", "days": 7})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert bad.error == "not_found" and bad.result is None


async def test_a_window_open_leaves_the_thermostat_alone(hass: HomeAssistant, entry, climate_calls) -> None:
    """Airing: Roost does not change the thermostat (it would heat the outdoors) and says why."""
    m = entry.runtime_data
    await m.async_set_mode("active")
    m.window.open_at = time.time()
    await m._async_control(time.time())
    await hass.async_block_till_done()
    assert not climate_calls and m.decision.why.code == "window_open" and m.reason.code == "window_open"


async def test_today_survives_a_restart(hass: HomeAssistant, entry) -> None:
    """Issue #2: the heating electricity and cost of today are kept over a restart; a saved earlier day starts at zero."""
    from homeassistant.util import dt as dt_util

    m = entry.runtime_data
    m._cost_day, m.cost_today, m.kwh_today = dt_util.now().date().isoformat(), 1.234, 4.56
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    m = entry.runtime_data
    assert (round(m.cost_today, 3), round(m.kwh_today, 2)) == (1.234, 4.56)
    assert hass.states.get("sensor.roost_heating_cost_today").state == "1.23"

    m._cost_day = "2020-01-01"
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    m = entry.runtime_data
    await m._async_tick(None)
    assert m._cost_day == dt_util.now().date().isoformat() and m.cost_today == 0.0


async def test_house_use_from_grid_and_solar(hass: HomeAssistant, quatt: str) -> None:
    """No sensor for the house: the usage profile comes from the grid meter and solar."""
    from datetime import timedelta
    from unittest.mock import patch

    from homeassistant.util import dt as dt_util

    from custom_components.roost_quatt import learning

    entry = await setup_roost(hass, quatt, {"has_solar": True, "grid_power": "sensor.grid", "pv_power": "sensor.pv"})
    hass.states.async_set("sensor.grid", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.pv", "0", {"unit_of_measurement": "kW"})
    end = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    hours = [end - timedelta(hours=i) for i in range(1, 15 * 24)]
    # every hour: 300 W from the grid and 0.2 kW of solar; the pv sensor is unavailable at night (no statistics)
    stats = {"sensor.grid": [{"start": t, "mean": 300.0} for t in hours],
             "sensor.pv": [{"start": t, "mean": 0.2} for t in hours if 6 <= dt_util.as_local(t).hour < 20]}
    m = entry.runtime_data
    m._weather = {int(t.timestamp()): (8.0, 0.2 if 6 <= dt_util.as_local(t).hour < 20 else 0.0, 3.0) for t in hours}
    with patch.object(learning.statistics, "statistics_during_period", return_value=stats), \
            patch.object(learning, "_async_archive", return_value=None):
        _rows, extra = await learning.async_rows(m)
    prof = extra["load_profile"]
    assert prof[12] == 0.5 and prof[2] == 0.3         # day: grid + solar; night: grid only


async def test_every_plan_hour_has_a_reason(hass: HomeAssistant, entry) -> None:
    """Issue #1: the planned-setpoint sensor carries a reason (code + values) for every hour of the plan."""
    a = hass.states.get(_plan_entity(hass)).attributes
    assert len(a["plan_why"]) == len(a["plan"])
    assert all(isinstance(code, str) and isinstance(args, dict) for code, args in a["plan_why"])


async def test_heating_curve_advice_sensor(hass: HomeAssistant, entry) -> None:
    """The advice on its sensor."""
    from custom_components.roost_quatt import curve

    m = entry.runtime_data
    m.curve_advice = curve.CurveAdvice(points=[[-20.0, 46.0, None], [9.0, 30.5, 31.5], [15.0, None, 31.9], [20.0, None, None],
                                               [25.0, None, None]], room=21.0, ua_kw=0.167, base_kw=-0.41, margin_kw=0.8,
                                       k_kw=0.209, n=1.1, cycling_from=8.0, days=142, hours=1880, out_min=-1.3, out_max=11.9,
                                       reliable=True, extrapolated=[-20.0])
    m._notify()
    await hass.async_block_till_done()
    st = next(s for s in hass.states.async_all("sensor") if s.entity_id.endswith("heating_curve_advice"))
    assert abs(float(st.state) - (46.0 + (30.5 - 46.0) * 20 / 29)) < 0.1            # 0 °C on the line from −20 to 9
    assert st.attributes["control"] == "opentherm" and st.attributes["points"][1][2] == 31.5
    assert st.attributes["cycling_from"] == 8.0 and st.attributes["heat_loss_w_per_k"] == 167


async def test_thermostat_gone_and_back_plans_once(hass: HomeAssistant, entry) -> None:
    """The thermostat unavailable (just after a start) and back: one 'back' event and one new plan, no loop."""
    m = entry.runtime_data
    hass.states.async_set(THERMOSTAT, "unavailable", {})
    await m._async_tick(None)
    thermostat(hass)
    await m._async_tick(None)
    await hass.async_block_till_done()
    assert sum(1 for e in m.events if e.get("kind") == "thermostat_back") == 1


async def test_explain_saving_service(hass: HomeAssistant, entry) -> None:
    """Issue #1: roost.explain_saving gives the saving per hour of the next 24 hours (and of a replayed day), with
    the plan changes; a recalculation that changes the plan is logged with why."""
    import pytest
    from homeassistant.exceptions import ServiceValidationError

    m = entry.runtime_data
    r = await hass.services.async_call("roost_quatt", "explain_saving", {"day": "next_24h"}, blocking=True, return_response=True)
    assert r["available"] and len(r["hours"]) == 24
    assert abs(sum(h["save"] for h in r["hours"]) + r["b_end"] - r["end"] - r["saving"]) < 0.02
    assert {"sp", "t", "kwh", "cost", "b_sp", "b_t", "b_kwh", "b_cost", "ts"} <= set(r["hours"][0])
    r = await hass.services.async_call("roost_quatt", "explain_saving", {}, blocking=True, return_response=True)
    assert r["available"] is False and "plan_changes" in r                 # no day replayed yet
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("roost_quatt", "explain_saving", {"day": "last tuesday"}, blocking=True, return_response=True)
    # the plan in force expected another setpoint now: the next plan logs the change
    snap = dict(m._plan_snap)
    m._plan_snap = {**snap, "sp": [x + 1.0 for x in snap["sp"]], "saving": snap["saving"] + 0.5}
    await m._async_tick(None, force_plan=True)
    line = m.plan_changes[-1]
    assert line["sp"][0] == snap["sp"][0] + 1.0 and line["why"]
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["plan_changes"] and diag["saving_explained"]["next_24h"]["hours"]


async def test_settings_from_the_card_do_not_reload(hass: HomeAssistant, entry) -> None:
    """21-10: a temperature changed in the card (roost.set_settings) reloaded Roost, and the card showed 'not
    available' for a moment: the update listener ran within async_update_entry and saw the old settings key."""
    m = entry.runtime_data
    await hass.services.async_call("roost_quatt", "set_settings", {"comfort": 21.0}, blocking=True)
    await hass.async_block_till_done()
    assert entry.runtime_data is m                                  # the same manager: no reload
    assert {**entry.data, **entry.options}["comfort"] == 21.0 and m.settings().comfort == 21.0
    assert hass.states.get(_plan_entity(hass)).state not in ("unknown", "unavailable")


async def test_an_update_replays_the_days_kept(hass: HomeAssistant, entry) -> None:
    """After an update that replays a day differently (planner.REPLAY_VERSION) the days still in the hourly log are
    replayed again, so the saving of the last week and of this month is counted one way."""
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    from custom_components.roost_quatt import planner

    m = entry.runtime_data
    start = dt_util.start_of_local_day(dt_util.now() - timedelta(days=1))
    day = start.date().isoformat()
    m.hour_log = [{"ts": int((start + timedelta(hours=h)).timestamp()), "T": 20.5, "E": 0.0, "sp": 20.5, "sp_t": 20.5,
                   "t_out": 5.0, "rad": 0.0, "hour": h, "wind": 3.5, "p_grid": 0.3, "p_own": 0.3, "own": 0.0,
                   "day": 7 <= h < 22, "e": 0.3, "q": 1.2} for h in range(24)]
    m.saving_days[day], m.replayed_with = 9.99, None                 # as an older version left it
    await m._async_replay_kept_days()
    assert m.saving_days[day] != 9.99 and day in m.saving_detail and m.saving_detail[day]["parts"]
    assert m.replayed_with == planner.REPLAY_VERSION


async def test_live_hours_are_kept_over_a_restart(hass: HomeAssistant, entry) -> None:
    """The seconds Roost counts from the CIC per hour go into its store (saved every hour), and back into the heat
    pump's hours after a restart: the history file itself is only written by the import and at night."""
    m = entry.runtime_data
    t0 = int(time.time() // 3600 - 3) * 3600
    m._last_tick = None
    for i in range(31):                                  # an hour seen in two-minute runs, the CIC in standby
        m._track_live(t0 + i * 120)
        m._last_tick = t0 + i * 120
    m._track_live(t0 + 3600 + 60)
    assert m.live_hours[t0] == {"heating_s_live": 0} and m._pump_hours[t0]["heating_s_live"] == 0
    await m.async_save()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    m2 = entry.runtime_data
    assert m2 is not m and m2._pump_hours[t0]["heating_s_live"] == 0 and t0 in m2.live_hours
