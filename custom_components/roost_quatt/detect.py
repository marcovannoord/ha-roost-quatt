"""Suggestions for the setup: the entities Roost probably needs, so a user mostly checks instead of searching.

Only suggestions (shown filled in, never saved without the user's submit), found by device class, unit, area and
common names (evcc, Nord Pool, Tibber, ENTSO-e, Frank Energie, Solcast, Predbat, AlphaESS, SolarEdge, …).
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from . import series

PV_WORDS = ("pv", "solar", "zon")
EXPORT_WORDS = ("feedin", "feed_in", "export", "teruglever", "terug")


def _area(hass: HomeAssistant, entity_id: str) -> str | None:
    ent = er.async_get(hass).async_get(entity_id)
    if ent is None:
        return None
    if ent.area_id:
        return ent.area_id
    dev = dr.async_get(hass).async_get(ent.device_id) if ent.device_id else None
    return dev.area_id if dev else None


def _device(hass: HomeAssistant, entity_id: str) -> str | None:
    ent = er.async_get(hass).async_get(entity_id)
    return ent.device_id if ent else None


def _sensors(hass: HomeAssistant, device_class: str | None = None) -> list:
    out = []
    for st in hass.states.async_all("sensor"):
        if st.state in ("unavailable", "unknown"):
            continue
        if device_class and st.attributes.get("device_class") != device_class:
            continue
        out.append(st)
    return out


def _has(eid: str, words) -> bool:
    e = eid.lower()
    return any(w in e for w in words)


def thermostat(hass: HomeAssistant) -> str | None:
    """The one climate entity that heats and does not cool (an air conditioner cools, dries or blows)."""
    found = [st.entity_id for st in hass.states.async_all("climate")
             if "heat" in (st.attributes.get("hvac_modes") or []) and not set(st.attributes.get("hvac_modes") or []) & {"cool", "dry", "fan_only"}]
    return found[0] if len(found) == 1 else None


LIVING = ("woonkamer", "living", "lounge", "huiskamer", "wohnzimmer", "salon", "sejour")


def room_sensor(hass: HomeAssistant, thermostat_id: str | None, heat_pump_device: str | None) -> str | None:
    """A temperature sensor in the thermostat's area (or, when the thermostat has none, in the living room), not of
    the thermostat, the heat pump or another climate device (an air conditioner measures at its own outlet)."""
    if not thermostat_id:
        return None
    area = _area(hass, thermostat_id)
    climate_devices = {_device(hass, st.entity_id) for st in hass.states.async_all("climate")}
    own = {_device(hass, thermostat_id), heat_pump_device} | climate_devices
    hp = dr.async_get(hass).async_get(heat_pump_device) if heat_pump_device else None
    if hp is not None:
        # every device of the Quatt integration entry: its thermostat device reads the room over OpenTherm (the
        # thermostat's own reading, not a separate sensor)
        dev_reg = dr.async_get(hass)
        for entry_id in hp.config_entries:
            own |= {d.id for d in dr.async_entries_for_config_entry(dev_reg, entry_id)}

    def in_area(eid: str) -> bool:
        a = _area(hass, eid)
        return a == area if area else bool(a) and _has(a, LIVING)
    found = [st.entity_id for st in _sensors(hass, "temperature")
             if in_area(st.entity_id) and _device(hass, st.entity_id) not in own
             and not _has(st.entity_id, ("outside", "outdoor", "buiten", "water", "dhw", "floor", "vloer"))]
    return found[0] if len(found) == 1 else (sorted(found, key=lambda e: ("temp" not in e, len(e)))[0] if found else None)


def prices(hass: HomeAssistant) -> tuple[str | None, str | None]:
    """(import, export) price sensors with a forecast in their attributes."""
    imp, exp = [], []
    for st in hass.states.async_all("sensor"):
        unit = str(st.attributes.get("unit_of_measurement") or "")
        if "kwh" not in unit.lower():
            continue
        if not series.find_slots(dict(st.attributes)):
            continue
        (exp if _has(st.entity_id, EXPORT_WORDS) else imp).append(st.entity_id)
    pick = lambda xs: sorted(xs, key=lambda e: (not _has(e, ("forecast", "grid", "import", "price", "tariff", "prijs")), len(e)))[0] if xs else None
    return pick(imp), pick(exp)


def energy(hass: HomeAssistant) -> dict[str, str]:
    """Solar, grid, battery and house power and the solar forecasts, as far as they can be told apart."""
    out: dict[str, str] = {}
    power = _sensors(hass, "power")
    pv = [s.entity_id for s in power if _has(s.entity_id, PV_WORDS) and not _has(s.entity_id, ("forecast", "battery", "accu", "string", "mppt"))]
    if pv:
        out["pv_power"] = sorted(pv, key=lambda e: (not _has(e, ("current", "production", "power")), len(e)))[0]
    family = _device(hass, out["pv_power"]) if "pv_power" in out else None
    same = lambda e: family is None or _device(hass, e) == family
    grid = [s.entity_id for s in power if _has(s.entity_id, ("grid", "net_power", "meter")) and same(s.entity_id)]
    if grid:
        out["grid_power"] = sorted(grid, key=len)[0]
    soc = [s.entity_id for s in _sensors(hass, "battery") if _has(s.entity_id, ("battery", "accu", "soc")) and same(s.entity_id)
           and not _has(s.entity_id, ("phone", "telefoon", "watch", "car", "auto", "vehicle"))]
    if soc and family is not None:
        out["battery_soc"] = sorted(soc, key=len)[0]
        bp = [s.entity_id for s in power if _has(s.entity_id, ("battery", "accu")) and _device(hass, s.entity_id) == _device(hass, out["battery_soc"])]
        if bp:
            out["battery_power"] = sorted(bp, key=len)[0]
    house = [s.entity_id for s in power if _has(s.entity_id, ("load", "house", "home", "huis", "consumption"))
             and not _has(s.entity_id, ("battery", "accu")) and same(s.entity_id)]
    if house:
        out["house_power"] = sorted(house, key=len)[0]
    kwh = [s for s in _sensors(hass) if str(s.attributes.get("unit_of_measurement") or "").lower() == "kwh"
           and _has(s.entity_id, ("forecast", "verwachting", "predbat", "solcast")) and _has(s.entity_id, PV_WORDS)]
    today = [s.entity_id for s in kwh if _has(s.entity_id, ("today", "vandaag"))]
    tomorrow = [s.entity_id for s in kwh if _has(s.entity_id, ("tomorrow", "morgen"))]
    if today:
        out["pv_forecast"] = sorted(today, key=len)[0]
    if tomorrow:
        out["pv_forecast_tomorrow"] = sorted(tomorrow, key=len)[0]
    return out


def friendly(hass: HomeAssistant, entity_id: str | None) -> str:
    st = hass.states.get(entity_id) if entity_id else None
    return (st.attributes.get("friendly_name") or entity_id) if st else (entity_id or "—")
