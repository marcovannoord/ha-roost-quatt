"""Fixtures: a Home Assistant with a recorder, a Quatt Duo (devices + sensors as the Quatt integration makes
them), an OpenTherm thermostat, a price sensor, and Roost set up on them.

The dashboard card is served through Home Assistant's web server and frontend, which are not part of a test run:
they are stood in for with mocks."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.frontend import DATA_EXTRA_JS_URL_ES5, DATA_EXTRA_MODULE_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

DOMAIN = "roost_quatt"
THERMOSTAT = "climate.living_room"
PRICE = "sensor.electricity_price"
QUATT_SENSORS = {   # (device, key) -> (state, unit, device_class), unique_id "<hub>:<device>:<key>"
    ("cic", "qc.supervisoryControlMode"): ("0", None, None),
    ("cic", "computedHeatPower"): ("0", "W", "power"),
    ("cic", "computedPower"): ("0", "W", "power"),
    ("cic", "computedPowerInput"): ("12", "W", "power"),
    ("cic", "computedQuattCop"): ("0", "CoP", None),
    ("heatpump_1", "hp1.powerInput"): ("6", "W", "power"),
    ("heatpump_1", "hp1.temperatureOutside"): ("6.0", "°C", "temperature"),
    ("heatpump_1", "hp1.temperatureWaterIn"): ("24.0", "°C", "temperature"),
    ("heatpump_1", "hp1.temperatureWaterOut"): ("24.5", "°C", "temperature"),
    ("heatpump_2", "hp2.powerInput"): ("6", "W", "power"),
    ("heatpump_2", "hp2.temperatureWaterOut"): ("24.5", "°C", "temperature"),
    ("thermostat", "thermostat.otFtControlSetpoint"): ("10", "°C", "temperature"),
    ("thermostat", "thermostat.otFtRoomSetpoint"): ("20.5", "°C", "temperature"),
    ("thermostat", "thermostat.otFtRoomTemperature"): ("20.6", "°C", "temperature"),
}
HUB = "cic-1234"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    """A recorder (it has to start before Home Assistant itself) and the integration from custom_components."""
    return


def prices(hass: HomeAssistant, base: float = 0.30) -> None:
    start = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    rates = [{"start": (start + timedelta(hours=i)).isoformat(), "end": (start + timedelta(hours=i + 1)).isoformat(),
              "value": base + (0.2 if 8 <= i <= 11 else 0.0)} for i in range(36)]
    hass.states.async_set(PRICE, str(base), {"unit_of_measurement": "EUR/kWh", "rates": rates})


def thermostat(hass: HomeAssistant, target: float = 20.5, room: float = 20.6) -> None:
    hass.states.async_set(THERMOSTAT, "heat", {"temperature": target, "current_temperature": room, "hvac_modes": ["heat", "off"]})


@pytest.fixture
async def quatt(hass: HomeAssistant) -> str:
    """A Quatt Duo with its devices and sensors, as the Quatt integration creates them. Returns the CIC's device id."""
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()
    hass.config.components.update({"http", "frontend", "lovelace"})
    hass.data[DATA_EXTRA_MODULE_URL] = set()
    hass.data[DATA_EXTRA_JS_URL_ES5] = set()
    qe = MockConfigEntry(domain="quatt", title="Quatt", unique_id=HUB, data={"ip_address": "192.0.2.10"})
    qe.add_to_hass(hass)
    dev_reg, reg = dr.async_get(hass), er.async_get(hass)
    devices = {d: dev_reg.async_get_or_create(config_entry_id=qe.entry_id, identifiers={("quatt", HUB if d == "cic" else f"{HUB}_{d}")},
                                              name=d.upper() if d == "cic" else d.replace("_", " ").title(), model="—")
               for d in ("cic", "heatpump_1", "heatpump_2", "thermostat")}
    for (d, key), (state, unit, dc) in QUATT_SENSORS.items():
        ent = reg.async_get_or_create("sensor", "quatt", f"{HUB}:{d}:{key}", config_entry=qe, device_id=devices[d].id,
                                      suggested_object_id=f"{d}_{key.replace('.', '_').lower()}")
        attrs = {"device_class": dc} if dc else {}
        if unit:
            attrs["unit_of_measurement"] = unit
        hass.states.async_set(ent.entity_id, state, attrs)
    thermostat(hass)
    prices(hass)
    return devices["cic"].id


async def setup_roost(hass: HomeAssistant, device_id: str, options: dict | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Roost", unique_id=device_id,
                            data={"heat_pump": device_id, "thermostat": THERMOSTAT, "import_price": PRICE,
                                  "import_history": False, "weather_source": "open_meteo"},
                            options=options or {})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
async def climate_calls(hass: HomeAssistant):
    return async_mock_service(hass, "climate", "set_temperature")


@pytest.fixture
async def entry(hass: HomeAssistant, quatt: str, climate_calls) -> MockConfigEntry:
    assert await async_setup_component(hass, "websocket_api", {})
    return await setup_roost(hass, quatt)
