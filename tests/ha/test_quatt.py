"""A Quatt heat pump: the setup's Quatt path, the Quatt integration's entities, the electricity without an energy
meter, the seconds of heating Roost counts itself, and no Weheat login anywhere."""
from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_entry_oauth2_flow, device_registry as dr
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.roost.diagnostics import async_get_config_entry_diagnostics
from custom_components.roost.manager import QuattManager

from .conftest import PRICE, THERMOSTAT
from .test_config_flow import COMFORT, start

DOMAIN = "roost"


async def test_setup_the_quatt_way(hass: HomeAssistant, quatt: str, current_request_with_host) -> None:
    """Quatt in the menu, then the CIC: no Weheat login page, even when the Weheat integration has an app registration."""
    config_entry_oauth2_flow.async_register_implementation(hass, "weheat", config_entry_oauth2_flow.LocalOAuth2Implementation(
        hass, "weheat", "weheat-client", "secret", "https://auth.example/authorize", "https://auth.example/token"))
    r = await start(hass, "quatt")
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"name": "Roost", "heat_pump": quatt, "thermostat": THERMOSTAT,
                                                                       "import_weheat_history": False})
    assert r["type"] is FlowResultType.FORM and r["step_id"] == "house"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"emitter": "floor", "use_bag": False})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"price_mode": "sensor", "import_price": PRICE})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"has_solar": False, "has_battery": False})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], COMFORT)
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert r["data"]["brand"] == "quatt" and r["data"]["heat_pump"] == quatt and "token" not in r["data"]


async def test_not_a_quatt_device(hass: HomeAssistant, quatt: str, weheat: str) -> None:
    """A device of another integration, or a Weheat heat pump picked on the Quatt screen."""
    other = MockConfigEntry(domain="demo")
    other.add_to_hass(hass)
    dev = dr.async_get(hass).async_get_or_create(config_entry_id=other.entry_id, identifiers={("demo", "x")}, name="Not a heat pump")
    for wrong in (dev.id, weheat):
        r = await start(hass, "quatt")
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"name": "Roost", "heat_pump": wrong, "thermostat": THERMOSTAT,
                                                                           "import_weheat_history": False})
        assert r["type"] is FlowResultType.FORM and r["errors"] == {"heat_pump": "not_quatt"}
    r = await start(hass, "weheat")
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"name": "Roost", "heat_pump": quatt, "thermostat": THERMOSTAT,
                                                                       "import_weheat_history": False})
    assert r["errors"] == {"heat_pump": "not_weheat"}


async def test_options_keep_the_brand_in_the_data(hass: HomeAssistant, quatt_entry) -> None:
    r = await hass.config_entries.options.async_init(quatt_entry.entry_id)
    r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "comfort"})
    r = await hass.config_entries.options.async_configure(r["flow_id"], {**COMFORT, "comfort": 21.0, "store_max": 23.0})
    assert r["type"] is FlowResultType.MENU
    assert quatt_entry.data["brand"] == "quatt" and "brand" not in quatt_entry.options


async def test_setup_finds_the_quatt_sensors_and_plans(hass: HomeAssistant, quatt_entry) -> None:
    m = quatt_entry.runtime_data
    assert isinstance(m, QuattManager) and m.brand == "quatt"
    assert {"state", "power_out", "power_in", "outdoor", "water_setpoint", "water_out", "power_in_hp2"} <= set(m.ent)
    assert m.pump_name == "Quatt Duo" and m.pump.source.startswith("profile quatt_duo")
    assert m.ent["water_out"].endswith("heatpump_2_hp2_temperaturewaterout")      # the Duo's second unit feeds the house
    st = next(s for s in hass.states.async_all("sensor") if s.entity_id.endswith("planned_setpoint"))
    assert st.state not in ("unknown", "unavailable") and len(st.attributes["plan"]) == 24
    assert "quatt_missing" not in m.health.issues
    assert [d.model for d in dr.async_entries_for_config_entry(dr.async_get(hass), quatt_entry.entry_id)] == ["Heating planner for Quatt"]


async def test_no_login_is_asked(hass: HomeAssistant, quatt_entry) -> None:
    """A Quatt is read through the Quatt integration's entities: no re-authenticate notice."""
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)


async def test_diagnostics(hass: HomeAssistant, quatt_entry) -> None:
    d = await async_get_config_entry_diagnostics(hass, quatt_entry)
    assert d["brand"] == "quatt" and d["quatt_entities"] and "quatt_info" in d and "weheat_pump" not in d


async def test_heating_curve_advice_for_a_quatt(hass: HomeAssistant, quatt_entry) -> None:
    from custom_components.roost import curve

    m = quatt_entry.runtime_data
    m.curve_advice = curve.CurveAdvice(points=[[-10.0, 40.0, None], [-5.0, 37.0, None], [0.0, 34.0, 33.5], [5.0, 31.0, None],
                                               [10.0, 28.0, None]], room=21.0, ua_kw=0.167, base_kw=-0.41, margin_kw=0.8,
                                       k_kw=0.209, n=1.1, cycling_from=8.0, days=142, hours=1880, out_min=-1.3, out_max=11.9,
                                       reliable=True, extrapolated=[-10.0])
    m._notify()
    await hass.async_block_till_done()
    st = next(s for s in hass.states.async_all("sensor") if s.entity_id.endswith("heating_curve_advice"))
    assert float(st.state) == 34.0
    assert st.attributes["brand"] == "quatt" and st.attributes["control"] == "opentherm" and st.attributes["current"] is None


def _heating(hass, m, watts) -> None:
    """The CIC heating with the units taking `watts` (a Quatt has no energy meter: Roost integrates the power)."""
    hass.states.async_set(m.ent["state"], "2")
    hass.states.async_set(m.ent["power_in"], str(watts) if watts is not None else "unavailable",
                          {"device_class": "power", "unit_of_measurement": "W"})


async def test_electricity_from_the_power_while_heating(hass, quatt_entry):
    """3 kW for 20 minutes is 1 kWh; at most 10 minutes count per run; a power reading briefly unavailable adds
    nothing, and its return adds only the time since the last run (not the gap)."""
    m = quatt_entry.runtime_data
    now = dt_util.as_utc(dt_util.now().replace(hour=11, minute=0, second=0, microsecond=0))   # an hour on: the same day
    t = now.timestamp()
    m._cost_day = dt_util.as_local(now).date().isoformat()
    before = m.kwh_today
    _heating(hass, m, 3000)
    m._last_tick = t - 600
    m._count_cost(now)
    m._last_tick = t
    m._count_cost(now + timedelta(minutes=10))
    assert m.kwh_today - before == pytest.approx(1.0)
    before = m.kwh_today
    _heating(hass, m, None)
    m._last_tick = t + 600
    m._count_cost(now + timedelta(minutes=12))
    assert m.kwh_today == before
    _heating(hass, m, 1200)
    m._last_tick = t + 3600 - 120
    m._count_cost(now + timedelta(hours=1))
    assert m.kwh_today - before == pytest.approx(1.2 * 120 / 3600)


async def test_standby_is_not_heating_electricity(hass, quatt_entry):
    """A Quatt standing still takes ~10 W: not counted as heating, as a heat pump's own meter for heating does."""
    m = quatt_entry.runtime_data
    now = dt_util.utcnow()
    m._cost_day = dt_util.as_local(now).date().isoformat()
    hass.states.async_set(m.ent["state"], "0")
    hass.states.async_set(m.ent["power_in"], "12", {"device_class": "power", "unit_of_measurement": "W"})
    m._last_tick = now.timestamp() - 120
    before = m.kwh_today
    m._count_cost(now)
    assert m.kwh_today == before


async def test_the_seconds_of_heating_are_counted_and_kept(hass, quatt_entry):
    """Each tick counts the CIC's state; a closed hour goes into the unit's hours and the small store."""
    m = quatt_entry.runtime_data
    hour = int(dt_util.utcnow().timestamp() // 3600 * 3600) - 7200
    _heating(hass, m, 3000)
    m._live.hour = None
    m._last_tick = None
    m._track_live(hour)
    for k in range(1, 16):                       # half an hour heating, then standing still
        m._last_tick = hour + (k - 1) * 120
        m._track_live(hour + k * 120)
    hass.states.async_set(m.ent["state"], "0")
    for k in range(16, 31):                      # the last tick is in the next hour: it closes this one
        m._last_tick = hour + (k - 1) * 120
        m._track_live(hour + k * 120)
    secs = m._pump_hours[hour]["heating_s_live"]
    assert 1700 < secs < 1900 and m.live_hours[hour]["heating_s_live"] == secs     # scaled to the whole hour
    assert str(hour) in m._brand_save()["live_hours"]


async def test_a_restart_within_the_hour_keeps_the_heating_seconds(hass, quatt_entry):
    m = quatt_entry.runtime_data
    t = dt_util.utcnow().timestamp()
    hour = int(t // 3600 * 3600)
    m._acc_hour = hour
    m._live.hour, m._live.heating_s, m._live.boiler_s, m._live.seen_s = hour, 900.0, 0.0, 1500.0
    saved = m._acc_state()
    m._live.hour, m._live.heating_s, m._live.seen_s = None, 0.0, 0.0
    m._restore_acc(saved, t + 60)
    assert m._live.hour == hour and m._live.heating_s == 900.0 and m._live.seen_s == 1500.0
    assert m._last_elec is None                       # a Quatt has no meter reading


async def test_the_quatt_missing_notice(hass, quatt_entry):
    """Without the CIC's state, heat and electricity: a notice in Quatt's words, gone when they are back."""
    from homeassistant.helpers import issue_registry as ir

    m = quatt_entry.runtime_data
    ent = dict(m.ent)
    m.ent = {k: v for k, v in ent.items() if k != "power_in"}
    m._check_health(dt_util.utcnow().timestamp())
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"{quatt_entry.entry_id}_quatt_missing")
    assert issue is not None and issue.translation_key == "quatt_missing"
    m.ent = ent
    m._check_health(dt_util.utcnow().timestamp())
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"{quatt_entry.entry_id}_quatt_missing") is None


async def test_weheat_and_quatt_side_by_side(hass: HomeAssistant, weheat: str, quatt: str, climate_calls) -> None:
    """Two heat pumps in one Home Assistant: each entry gets the manager of its brand; an entry from before the brand
    was asked is a Weheat one."""
    from homeassistant.setup import async_setup_component

    from custom_components.roost.manager import WeheatManager

    from .conftest import setup_roost

    assert await async_setup_component(hass, "websocket_api", {})
    old = await setup_roost(hass, weheat)
    new = await setup_roost(hass, quatt, data={"brand": "quatt"})
    assert isinstance(old.runtime_data, WeheatManager) and old.runtime_data.brand == "weheat"
    assert isinstance(new.runtime_data, QuattManager)
    assert "elec" in old.runtime_data.ent and "power_in_hp2" in new.runtime_data.ent
