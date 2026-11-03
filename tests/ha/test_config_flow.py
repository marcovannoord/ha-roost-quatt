"""The setup screens: by subject, with the regulation folded away, and the options menu."""
from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_entry_oauth2_flow, device_registry as dr
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import PRICE, THERMOSTAT

DOMAIN = "roost"
COMFORT = {"day_from": 7, "day_to": 22, "comfort": 20.5, "day_min": 20.0, "night_min": 19.0, "store_max": 22.5,
           "advanced": {"lowest_setpoint": 19.0, "max_above_room": 1.0, "min_interval": 60, "pause_hours": 2,
                        "baseline_night": 0, "weather_source": "open_meteo"}}


async def start(hass: HomeAssistant, brand: str = "weheat") -> dict:
    """The first screen asks whose heat pump it is; then that brand's screen."""
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert r["type"] is FlowResultType.MENU and r["step_id"] == "user" and r["menu_options"] == ["weheat", "quatt"]
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"next_step_id": brand})
    assert r["type"] is FlowResultType.FORM and r["step_id"] == brand
    return r


async def _to_comfort(hass: HomeAssistant, weheat: str, solar: bool = False) -> dict:
    r = await start(hass)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"name": "Roost", "heat_pump": weheat, "thermostat": THERMOSTAT,
                                                                       "import_weheat_history": False})
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


async def test_full_flow(hass: HomeAssistant, weheat: str) -> None:
    r = await _to_comfort(hass, weheat, solar=True)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], COMFORT)
    assert r["type"] is FlowResultType.CREATE_ENTRY and r["title"] == "Roost"
    d = r["data"]
    assert d["brand"] == "weheat" and d["heat_pump"] == weheat and d["thermostat"] == THERMOSTAT and d["import_price"] == PRICE
    assert d["max_above_room"] == 1.0 and "advanced" not in d                # the section is stored flat


async def test_fixed_price(hass: HomeAssistant, weheat: str) -> None:
    r = await start(hass)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"name": "Roost", "heat_pump": weheat, "thermostat": THERMOSTAT,
                                                                       "import_weheat_history": False})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"emitter": "radiators", "use_bag": False})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"price_mode": "sensor"})
    assert r["type"] is FlowResultType.FORM and r["errors"] == {"import_price": "price_needed"}
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"price_mode": "fixed"})
    assert r["step_id"] == "price_fixed"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"fixed_price": 0.30, "fixed_low_price": 0.25, "low_from": 23,
                                                                       "low_to": 7, "low_weekend": True})
    assert r["step_id"] == "solar"


async def test_not_a_weheat_device(hass: HomeAssistant, weheat: str) -> None:
    other = MockConfigEntry(domain="demo")
    other.add_to_hass(hass)
    dev = dr.async_get(hass).async_get_or_create(config_entry_id=other.entry_id, identifiers={("demo", "x")}, name="Not a heat pump")
    r = await start(hass)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"name": "Roost", "heat_pump": dev.id, "thermostat": THERMOSTAT,
                                                                       "import_weheat_history": False})
    assert r["type"] is FlowResultType.FORM and r["errors"] == {"heat_pump": "not_weheat"}


async def test_comfort_checks(hass: HomeAssistant, weheat: str) -> None:
    r = await _to_comfort(hass, weheat)
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


async def test_options_never_copy_the_weheat_login(hass: HomeAssistant, entry) -> None:
    hass.config_entries.async_update_entry(entry, data={**entry.data, "weheat_auth": "own", "auth_implementation": "roost_x",
                                                        "token": {"access_token": "a", "refresh_token": "r", "expires_at": 0}})
    await hass.async_block_till_done()
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "comfort"})
    r = await hass.config_entries.options.async_configure(r["flow_id"], {**COMFORT, "comfort": 21.0, "store_max": 23.0})
    assert r["type"] is FlowResultType.MENU
    assert not {"token", "auth_implementation", "weheat_auth"} & set(entry.options) and entry.data["token"]["access_token"] == "a"


def _weheat_registration(hass: HomeAssistant) -> None:
    """The app registration the Weheat integration has (application credentials), as Roost finds it."""
    config_entry_oauth2_flow.async_register_implementation(hass, "weheat", config_entry_oauth2_flow.LocalOAuth2Implementation(
        hass, "weheat", "weheat-client", "secret", "https://auth.example/authorize", "https://auth.example/token"))


async def test_setup_logs_in_with_the_weheat_account(hass: HomeAssistant, weheat: str, current_request_with_host) -> None:
    """After the first screen Weheat's login page: nothing to fill in, the Weheat integration's app registration."""
    _weheat_registration(hass)
    r = await start(hass)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"name": "Roost", "heat_pump": weheat, "thermostat": THERMOSTAT,
                                                                       "import_weheat_history": False})
    assert r["type"] is FlowResultType.EXTERNAL_STEP
    assert r["url"].startswith("https://auth.example/authorize") and "client_id=weheat-client" in r["url"]


async def test_reauth_logs_in_again(hass: HomeAssistant, entry, current_request_with_host) -> None:
    _weheat_registration(hass)
    r = await entry.start_reauth_flow(hass)
    assert r["type"] is FlowResultType.FORM and r["step_id"] == "reauth_confirm"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
    assert r["type"] is FlowResultType.EXTERNAL_STEP and "client_id=weheat-client" in r["url"]


async def test_reauth_without_an_app_registration(hass: HomeAssistant, entry) -> None:
    """No Weheat integration app registration: Home Assistant asks for application credentials for Roost."""
    assert await async_setup_component(hass, "application_credentials", {})
    r = await entry.start_reauth_flow(hass)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "missing_credentials"


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
    reload; the Weheat login in the data stays."""
    hass.config_entries.async_update_entry(entry, data={**entry.data, "pv_power": "sensor.pv", "grid_power": "sensor.grid",
                                                         "battery_soc": "sensor.soc", "house_power": "sensor.house",
                                                         "token": {"access_token": "x"}})
    await hass.async_block_till_done()
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "solar"})
    r = await hass.config_entries.options.async_configure(r["flow_id"], {
        "solar_section": {"has_solar": True, "pv_power": "sensor.pv", "grid_power": "sensor.grid", "grid_sign": "import_positive"},
        "battery_section": {"has_battery": True, "battery_soc": "sensor.soc"},
        "grid_preference": 0.0})
    assert r["type"] is FlowResultType.MENU
    conf = {**entry.data, **entry.options}
    assert "house_power" not in conf and conf["battery_soc"] == "sensor.soc" and entry.data["token"] == {"access_token": "x"}


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


async def test_built_in_day_ahead_prices_screen(hass: HomeAssistant, weheat: str) -> None:
    r = await start(hass)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"name": "Roost", "heat_pump": weheat, "thermostat": THERMOSTAT,
                                                                       "import_weheat_history": False})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"emitter": "floor", "use_bag": False})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"price_mode": "epex"})      # no sensor needed
    assert r["type"] is FlowResultType.FORM and r["step_id"] == "price_epex"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"epex_zone": "NL", "import_mult": 1.21, "import_add": 0.15,
                                                                       "export_formula": True, "export_mult": 1.0, "export_add": -0.02})
    assert r["step_id"] == "solar"
