"""Roost for Quatt: smart heating planner for Quatt heat pumps (a fork of Roost by Akashironld, MIT)."""
from __future__ import annotations

import hashlib
import json
import logging
import time
import traceback
from collections import deque
from datetime import datetime
from pathlib import Path

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, UnitOfTemperature
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er, issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .const import CARD_URL, CONF_COMFORT, CONF_THERMOSTAT, DEFAULTS, DOMAIN, STORAGE_VERSION
from .manager import RoostManager

_LOGGER = logging.getLogger(__name__)


class RecentLog(logging.Handler):
    """The last warnings and errors of Roost's own loggers, for the diagnostics download (a bug report)."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.records: deque = deque(maxlen=60)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            exc = "".join(traceback.format_exception(*record.exc_info))[-1200:] if record.exc_info else None
            self.records.append({"t": datetime.fromtimestamp(record.created).isoformat(timespec="seconds"), "level": record.levelname,
                                 "logger": record.name, "message": record.getMessage()[:600], "exception": exc})
        except Exception:  # noqa: BLE001 - never break logging
            pass


def recent_log(hass: HomeAssistant) -> RecentLog:
    data = hass.data.setdefault(DOMAIN, {})
    if "recent_log" not in data:
        handler = RecentLog()
        logging.getLogger(__package__).addHandler(handler)
        data["recent_log"] = handler
    return data["recent_log"]

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SELECT, Platform.BUTTON]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type RoostConfigEntry = ConfigEntry[RoostManager]


@websocket_api.websocket_command({vol.Required("type"): "roost_quatt/history", vol.Required("entity_id"): str,
                                  vol.Optional("days", default=7): vol.All(int, vol.Range(min=1, max=7))})
@websocket_api.async_response
async def _ws_history(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """The look back for the card: the hours, events and days of the Roost that owns this entity."""
    ent = er.async_get(hass).async_get(msg["entity_id"])
    entry = hass.config_entries.async_get_entry(ent.config_entry_id) if ent and ent.config_entry_id else None
    mgr = getattr(entry, "runtime_data", None) if entry and entry.domain == DOMAIN else None
    if mgr is None:
        connection.send_error(msg["id"], "not_found", "No Roost for this entity")
        return
    connection.send_result(msg["id"], mgr.history_payload(msg["days"]))


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the dashboard card, register the services and the card's look back (websocket)."""
    websocket_api.async_register_command(hass, _ws_history)
    card = Path(__file__).parent / "frontend" / "roost-quatt-card.js"
    await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(card), True)])
    version = hass.data.setdefault(DOMAIN, {}).get("version")
    if version is None:
        from homeassistant.loader import async_get_integration
        version = str((await async_get_integration(hass, DOMAIN)).version)
        hass.data[DOMAIN]["version"] = version
    # the version plus a fingerprint of the file: a browser fetches the card again whenever it changed, also within a
    # version (a test build, a zip installed over the same version)
    digest = await hass.async_add_executor_job(lambda: hashlib.sha1(card.read_bytes()).hexdigest()[:8])
    url = f"{CARD_URL}?v={version}-{digest}"
    add_extra_js_url(hass, url, es5=True)             # legacy frontend (older browsers, wall tablets)
    if _resources(hass) is not None:
        # Dashboards managed in the UI: the card only as a dashboard resource (an early start-page module can be
        # invisible after Home Assistant 2026.9 swaps in its scoped element registry, mostly in the mobile apps).
        hass.async_create_task(_async_card_as_resource(hass, url))
    else:
        add_extra_js_url(hass, url)

    def managers() -> list[RoostManager]:
        return [m for e in hass.config_entries.async_entries(DOMAIN) if isinstance(m := getattr(e, "runtime_data", None), RoostManager)]

    def targets(call: ServiceCall) -> list[RoostManager]:
        ms = managers()
        if not ms:
            raise ServiceValidationError("Roost is not set up")
        return ms

    async def pause(call: ServiceCall) -> None:
        for m in targets(call):
            await m.async_pause(call.data["hours"])

    async def resume(call: ServiceCall) -> None:
        for m in targets(call):
            await m.async_resume()

    async def away(call: ServiceCall) -> None:
        if call.data.get("until") is not None:
            until = dt_util.as_utc(call.data["until"]).timestamp()
        else:
            until = time.time() + float(call.data.get("days", 1.0)) * 86400
        for m in targets(call):
            await m.async_away(until, call.data.get("minimum"))

    async def home(call: ServiceCall) -> None:
        for m in targets(call):
            await m.async_home()

    async def set_settings(call: ServiceCall) -> None:
        for m in targets(call):
            await m.async_set_settings(**dict(call.data))

    async def import_history(call: ServiceCall) -> None:
        for m in targets(call):
            m.spawn(m.async_import(int(call.data["days"])), "import from the statistics")

    async def explain_saving(call: ServiceCall) -> ServiceResponse:
        day = call.data["day"]
        if day not in ("yesterday", "next_24h"):
            try:
                day = cv.date(day).isoformat()
            except vol.Invalid as err:
                raise ServiceValidationError("day: yesterday, next_24h or a date (YYYY-MM-DD)") from err
        ms = targets(call)
        if len(ms) == 1:
            return ms[0].explain_saving(day)
        return {"entries": [{"entry": m.entry.title, **m.explain_saving(day)} for m in ms]}

    hass.services.async_register(DOMAIN, "pause", pause, vol.Schema({vol.Optional("hours", default=2): vol.All(vol.Coerce(float), vol.Range(min=0.25, max=72))}))
    hass.services.async_register(DOMAIN, "resume", resume, vol.Schema({}))
    hass.services.async_register(DOMAIN, "away", away, vol.Schema({
        vol.Optional("until"): cv.datetime, vol.Optional("days"): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=60)),
        vol.Optional("minimum"): vol.All(vol.Coerce(float), vol.Range(min=5, max=20))}))
    hass.services.async_register(DOMAIN, "home", home, vol.Schema({}))
    temp = lambda lo, hi: vol.All(vol.Coerce(float), vol.Range(min=lo, max=hi))      # noqa: E731
    hour = lambda lo, hi: vol.All(vol.Coerce(int), vol.Range(min=lo, max=hi))        # noqa: E731
    hass.services.async_register(DOMAIN, "set_settings", set_settings, vol.Schema({
        vol.Optional("comfort"): temp(15, 25), vol.Optional("day_min"): temp(10, 25), vol.Optional("night_min"): temp(5, 25),
        vol.Optional("store_max"): temp(15, 28), vol.Optional("lowest_setpoint"): temp(5, 25),
        vol.Optional("day_from"): hour(0, 23), vol.Optional("day_to"): hour(1, 24)}))
    hass.services.async_register(DOMAIN, "explain_saving", explain_saving, vol.Schema({vol.Optional("day", default="yesterday"): str}),
                                 supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "import_history", import_history,
                                 vol.Schema({vol.Optional("days", default=365): vol.All(vol.Coerce(int), vol.Range(min=7, max=365))}))
    return True


def _resources(hass: HomeAssistant):
    """The dashboard resources, when they are managed in the UI (not in YAML).

    Home Assistant keeps them under hass.data["lovelace"]: a dict up to early 2025, an object since. Only the
    storage collection can be changed; YAML resources are left alone."""
    try:
        from homeassistant.components.lovelace.resources import ResourceStorageCollection
    except ImportError:  # pragma: no cover - very old or changed Home Assistant
        return None
    data = hass.data.get("lovelace")
    res = data.get("resources") if isinstance(data, dict) else getattr(data, "resources", None)
    return res if isinstance(res, ResourceStorageCollection) else None


async def _async_card_as_resource(hass: HomeAssistant, url: str) -> None:
    if not await _async_register_resource(hass, url):
        add_extra_js_url(hass, url)                     # could not add the resource: fall back to the start page


async def _async_register_resource(hass: HomeAssistant, url: str) -> bool:
    """Add the card to the dashboard resources, or bring its version up to date. True when it is there."""
    res = _resources(hass)
    if res is None:
        return False
    try:
        await res.async_get_info()                       # loads the collection
        for item in res.async_items():
            if str(item.get("url", "")).split("?")[0] == CARD_URL:
                if item.get("url") != url or item.get("type") != "module":     # stored as "type"
                    await res.async_update_item(item["id"], {"res_type": "module", "url": url})
                return True
        await res.async_create_item({"res_type": "module", "url": url})
        return True
    except Exception:  # noqa: BLE001 - the card then loads from the start page
        _LOGGER.warning("Could not add the Roost card to the dashboard resources", exc_info=True)
        return False


async def async_setup_entry(hass: HomeAssistant, entry: RoostConfigEntry) -> bool:
    recent_log(hass)
    manager = RoostManager(hass, entry)
    entry.runtime_data = manager
    await manager.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    manager.conf_key = _conf_key(entry)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RoostConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.async_stop()
    return ok


async def async_remove_entry(hass: HomeAssistant, entry: RoostConfigEntry) -> None:
    """Removed by the user: the thermostat back on comfort when Roost was steering, its repair notices go, and the
    dashboard resource with the last one."""
    try:
        data = await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_load() or {}
        conf = {**DEFAULTS, **entry.data, **entry.options}
        st = hass.states.get(conf.get(CONF_THERMOSTAT, ""))
        if data.get("mode") == "active" and st is not None and st.state not in ("unavailable", "unknown"):
            t = float(conf[CONF_COMFORT])
            if hass.config.units.temperature_unit == UnitOfTemperature.FAHRENHEIT:
                t = round(t * 9 / 5 + 32)
            await hass.services.async_call("climate", "set_temperature", {"entity_id": conf[CONF_THERMOSTAT], "temperature": t},
                                           blocking=True)
    except Exception:  # noqa: BLE001 - removing goes on
        _LOGGER.warning("Roost could not set the thermostat back to comfort on removal", exc_info=True)
    if not [e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id]:
        if (res := _resources(hass)) is not None:
            try:
                await res.async_get_info()
                for item in res.async_items():
                    if str(item.get("url", "")).split("?")[0] == CARD_URL:
                        await res.async_delete_item(item["id"])
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Could not remove the card from the dashboard resources", exc_info=True)
    for issue_id in [i for (d, i) in ir.async_get(hass).issues if d == DOMAIN and i.startswith(entry.entry_id)]:
        ir.async_delete_issue(hass, DOMAIN, issue_id)


def _conf_key(entry: RoostConfigEntry, options: dict | None = None) -> str:
    """The settings, without anything that changes on its own (refreshed in the entry now and then: no reason to reload).
    options: the options about to be saved (the update listener can run before async_update_entry returns)."""
    return json.dumps({"data": {k: v for k, v in entry.data.items() if k != "token"},
                       "options": dict(entry.options if options is None else options),
                       "rooms": {sid: dict(sub.data) for sid, sub in entry.subentries.items()}}, sort_keys=True, default=str)


async def _reload(hass: HomeAssistant, entry: RoostConfigEntry) -> None:
    mgr = getattr(entry, "runtime_data", None)
    if mgr is not None and getattr(mgr, "conf_key", None) == _conf_key(entry):
        return
    await hass.config_entries.async_reload(entry.entry_id)
