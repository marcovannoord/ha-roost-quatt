"""The setup screens: by subject, with the regulation folded away, and the options menu."""
from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import PRICE, THERMOSTAT

DOMAIN = "roost_quatt"
COMFORT = {"day_from": 7, "day_to": 22, "comfort": 20.5, "day_min": 20.0, "night_min": 19.0, "store_max": 22.5,
           "advanced": {"lowest_setpoint": 19.0, "max_above_room": 1.0, "min_interval": 60, "pause_hours": 2,
                        "baseline_night": 0, "weather_source": "open_meteo"}}


async def _to_comfort(hass: HomeAssistant, quatt: str, solar: bool = False) -> dict:
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert r["type"] is FlowResultType.FORM and r["step_id"] == "user"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"name": "Roost", "heat_pump": quatt, "thermostat": THERMOSTAT,
                                                                       "import_history": False})
    assert r["step_id"] == "house"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"emitter": "floor", "use_bag": False})
    assert r["step_id"] == "price"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"price_mode": "sensor", "import_price": PRICE})
    assert r["step_id"] == "solar"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"has_solar": solar, "has_battery": False})
    if solar:
        assert r["step_id"] == "solar_details"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"grid_sign": "import_positive"})
    assert r["step_id"] == "comfort"
    return r


async def test_full_flow(hass: HomeAssistant, quatt: str) -> None:
    r = await _to_comfort(hass, quatt, solar=True)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], COMFORT)
    assert r["type"] is FlowResultType.CREATE_ENTRY and r["title"] == "Roost"
    d = r["data"]
    assert d["heat_pump"] == quatt and d["thermostat"] == THERMOSTAT and d["import_price"] == PRICE
    assert d["max_above_room"] == 1.0 and "advanced" not in d                # the section is stored flat


async def test_fixed_price(hass: HomeAssistant, quatt: str) -> None:
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"name": "Roost", "heat_pump": quatt, "thermostat": THERMOSTAT,
                                                                       "import_history": False})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"emitter": "radiators", "use_bag": False})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"price_mode": "sensor"})
    assert r["type"] is FlowResultType.FORM and r["errors"] == {"import_price": "price_needed"}
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"price_mode": "fixed"})
    assert r["step_id"] == "price_fixed"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"fixed_price": 0.30, "fixed_low_price": 0.25, "low_from": 23,
                                                                       "low_to": 7, "low_weekend": True})
    assert r["step_id"] == "solar"


async def test_not_a_quatt_device(hass: HomeAssistant, quatt: str) -> None:
    other = MockConfigEntry(domain="demo")
    other.add_to_hass(hass)
    dev = dr.async_get(hass).async_get_or_create(config_entry_id=other.entry_id, identifiers={("demo", "x")}, name="Not a heat pump")
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"name": "Roost", "heat_pump": dev.id, "thermostat": THERMOSTAT,
                                                                       "import_history": False})
    assert r["type"] is FlowResultType.FORM and r["errors"] == {"heat_pump": "not_quatt"}


async def test_comfort_checks(hass: HomeAssistant, quatt: str) -> None:
    r = await _to_comfort(hass, quatt)
    bad = {**COMFORT, "comfort": 19.5, "store_max": 19.0}
    r = await hass.config_entries.flow.async_configure(r["flow_id"], bad)
    assert r["type"] is FlowResultType.FORM
    assert r["errors"] == {"comfort": "comfort_below_min", "store_max": "store_below_comfort"}


async def test_options_menu_saves_each_part(hass: HomeAssistant, entry) -> None:
    r = await hass.config_entries.options.async_init(entry.entry_id)
    assert r["type"] is FlowResultType.MENU and r["menu_options"] == ["mode", "house", "price", "solar", "comfort", "notify", "done"]
    assert "comfort" in r["description_placeholders"] and r["description_placeholders"]["saved"] == ""
    r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "comfort"})
    r = await hass.config_entries.options.async_configure(r["flow_id"], {**COMFORT, "comfort": 21.0, "store_max": 23.0})
    # saved right away, back in the menu (closing the window loses nothing); Done closes
    assert r["type"] is FlowResultType.MENU and "Comfort" in r["description_placeholders"]["saved"]
    assert entry.options["comfort"] == 21.0
    r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "done"})
    assert r["type"] is FlowResultType.CREATE_ENTRY and entry.options["comfort"] == 21.0


async def test_options_solar_and_battery_on_one_screen(hass: HomeAssistant, entry) -> None:
    """Both blocks with their sensors on one screen; a tick turned off forgets that block's sensors."""
    hass.config_entries.async_update_entry(entry, options={"pv_power": "sensor.pv", "grid_power": "sensor.grid",
                                                           "battery_soc": "sensor.soc", "battery_kwh": 10.0})
    await hass.async_block_till_done()
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "solar"})
    assert r["type"] is FlowResultType.FORM and r["step_id"] == "solar"
    r = await hass.config_entries.options.async_configure(r["flow_id"], {
        "solar_section": {"has_solar": True, "pv_power": "sensor.pv", "grid_power": "sensor.grid", "grid_sign": "import_positive"},
        "battery_section": {"has_battery": False, "battery_soc": "sensor.soc", "battery_kwh": 10.0},
        "grid_preference": 0.0})
    assert r["type"] is FlowResultType.MENU
    assert entry.options["pv_power"] == "sensor.pv" and "battery_soc" not in entry.options and "battery_kwh" not in entry.options


async def test_options_a_field_left_empty_is_gone(hass: HomeAssistant, entry) -> None:
    """#3: House power filled in at the setup (the entry's data), left empty in Configure: it is gone, also after a
    reload."""
    hass.config_entries.async_update_entry(entry, data={**entry.data, "pv_power": "sensor.pv", "grid_power": "sensor.grid",
                                                         "battery_soc": "sensor.soc", "house_power": "sensor.house"})
    await hass.async_block_till_done()
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "solar"})
    r = await hass.config_entries.options.async_configure(r["flow_id"], {
        "solar_section": {"has_solar": True, "pv_power": "sensor.pv", "grid_power": "sensor.grid", "grid_sign": "import_positive"},
        "battery_section": {"has_battery": True, "battery_soc": "sensor.soc"},
        "grid_preference": 0.0})
    assert r["type"] is FlowResultType.MENU
    conf = {**entry.data, **entry.options}
    assert "house_power" not in conf and conf["battery_soc"] == "sensor.soc"


async def test_options_battery_use(hass: HomeAssistant, entry) -> None:
    """The battery is kept for the house unless the user chooses to let the heat pump use it when that is cheaper."""
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "solar"})
    r = await hass.config_entries.options.async_configure(r["flow_id"], {
        "solar_section": {"has_solar": False},
        "battery_section": {"has_battery": True, "battery_soc": "sensor.soc"},
        "grid_preference": 0.0})
    assert entry.options["battery_use"] == "house"
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "solar"})
    r = await hass.config_entries.options.async_configure(r["flow_id"], {
        "solar_section": {"has_solar": False},
        "battery_section": {"has_battery": True, "battery_soc": "sensor.soc", "battery_use": "cheaper"},
        "grid_preference": 0.0})
    assert entry.options["battery_use"] == "cheaper"


async def test_options_an_emptied_field_is_not_filled_in_again(hass: HomeAssistant, entry) -> None:
    """#3, again: a house power sensor Roost can detect by its name, emptied in Configure, is not suggested again
    when Configure is opened later (and so not saved again with the next change)."""
    hass.states.async_set("sensor.house_power", "450", {"device_class": "power", "unit_of_measurement": "W"})
    hass.config_entries.async_update_entry(entry, data={**entry.data, "pv_power": "sensor.pv", "grid_power": "sensor.grid",
                                                         "battery_soc": "sensor.soc", "house_power": "sensor.house_power"})
    await hass.async_block_till_done()
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "solar"})
    r = await hass.config_entries.options.async_configure(r["flow_id"], {
        "solar_section": {"has_solar": True, "pv_power": "sensor.pv", "grid_power": "sensor.grid", "grid_sign": "import_positive"},
        "battery_section": {"has_battery": True, "battery_soc": "sensor.soc"},
        "grid_preference": 0.0})
    assert "house_power" not in {**entry.data, **entry.options}
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "solar"})
    battery = next(v for k, v in r["data_schema"].schema.items() if str(k) == "battery_section")
    suggested = {str(k): (k.description or {}).get("suggested_value") for k in battery.schema.schema}
    assert suggested.get("house_power") is None and suggested.get("battery_soc") == "sensor.soc", suggested


async def test_built_in_day_ahead_prices_screen(hass: HomeAssistant, quatt: str) -> None:
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"name": "Roost", "heat_pump": quatt, "thermostat": THERMOSTAT,
                                                                       "import_history": False})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"emitter": "floor", "use_bag": False})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"price_mode": "epex"})      # no sensor needed
    assert r["type"] is FlowResultType.FORM and r["step_id"] == "price_epex"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"epex_zone": "NL", "import_mult": 1.21, "import_add": 0.15,
                                                                       "export_formula": True, "export_mult": 1.0, "export_add": -0.02})
    assert r["step_id"] == "solar"
