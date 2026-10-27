"""Collect the hourly history for learning: Home Assistant statistics, the heat pump's hours and past weather."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from homeassistant.components.recorder import get_instance, statistics
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from . import battery, history, value, weather as om
from .const import (CONF_BATTERY_KWH, CONF_BATTERY_POWER, CONF_BATTERY_SOC, CONF_GRID_POWER, CONF_GRID_SIGN, CONF_HOUSE_POWER, CONF_PV_POWER,
                    CONF_ROOM, HISTORY_DAYS)

if TYPE_CHECKING:
    from .manager import RoostManager

_LOGGER = logging.getLogger(__name__)
ENERGY_ROLES = ("heat", "heat_defrost", "elec", "elec_defrost", "elec_dhw")


def _ts(v) -> int:
    return int(v.timestamp() if isinstance(v, datetime) else float(v))


def _to_kw(hass, eid: str) -> float:
    """Factor from the sensor's unit to kW (W unless it says otherwise)."""
    st = hass.states.get(eid)
    return 0.001 if st is None or str(st.attributes.get("unit_of_measurement", "W")).lower() == "w" else 1.0


def _derive_house(conf: dict) -> bool:
    """No sensor for the house itself: work it out from the grid meter and solar (and the battery, when there is one)."""
    return (not conf.get(CONF_HOUSE_POWER) and bool(conf.get(CONF_GRID_POWER)) and bool(conf.get(CONF_PV_POWER))
            and (bool(conf.get(CONF_BATTERY_POWER)) or not conf.get(CONF_BATTERY_SOC)))


async def _async_archive(mgr: "RoostManager", start: datetime, end: datetime) -> None:
    """Fill the weather cache for [start, end) from the Open-Meteo archive (90 days per request)."""
    have = mgr._weather_hist
    t = start
    session = async_get_clientsession(mgr.hass)
    changed = False
    while t < end:
        t2 = min(end, t + timedelta(days=90))
        probe = [int(x) for x in range(int(t.timestamp()) // 3600 * 3600, int(t2.timestamp()), 6 * 3600)]
        if sum(1 for p in probe if len(have.get(p, ())) >= 5) >= 0.9 * len(probe):    # 5: with direct/diffuse (v0.3)
            t = t2
            continue
        url = om.ARCHIVE.format(lat=mgr.hass.config.latitude, lon=mgr.hass.config.longitude,
                                start=t.date().isoformat(), end=(t2 - timedelta(hours=1)).date().isoformat())
        try:
            async with session.get(url, timeout=60) as r:
                r.raise_for_status()
                have.update(om.parse(await r.json()))
                changed = True
        except Exception as err:  # noqa: BLE001 - learn with what there is
            _LOGGER.warning("Roost: weather archive %s – %s not available: %s", t.date(), t2.date(), err)
        t = t2
    if changed:
        await mgr._async_save_history()


async def async_hourly_means(mgr: "RoostManager", entity_ids: list[str], days: int) -> dict[str, dict[int, float]]:
    """Hourly means from Home Assistant's long-term statistics: {entity: {hour ts: mean}}."""
    end = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)
    stats = await get_instance(mgr.hass).async_add_executor_job(
        statistics.statistics_during_period, mgr.hass, start, end, set(entity_ids), "hour", None, {"mean"})
    return {eid: {_ts(r["start"]): float(r["mean"]) for r in stats.get(eid, []) if r.get("mean") is not None} for eid in entity_ids}


async def async_battery(mgr: "RoostManager", days: int = 14) -> battery.BatteryHabits | None:
    """The home battery's habits (battery.py) from the 5-minute statistics Home Assistant keeps (about ten days, as
    long as the recorder keeps its history). None without a battery or without statistics."""
    conf, hass = mgr.conf, mgr.hass
    ids = {role: conf[key] for role, key in (("battery", CONF_BATTERY_POWER), ("grid", CONF_GRID_POWER), ("pv", CONF_PV_POWER),
                                             ("soc", CONF_BATTERY_SOC)) if conf.get(key)}
    if "soc" not in ids and "battery" not in ids:
        return None
    end = dt_util.utcnow().replace(second=0, microsecond=0)
    stats = await get_instance(hass).async_add_executor_job(
        statistics.statistics_during_period, hass, end - timedelta(days=days), end, set(ids.values()), "5minute", None, {"mean"})
    k = {role: (1.0 if role == "soc" else _to_kw(hass, eid)) for role, eid in ids.items()}
    sign = 1.0 if conf.get(CONF_GRID_SIGN, "import_positive") == "import_positive" else -1.0
    by_t: dict[int, dict] = defaultdict(dict)
    for role, eid in ids.items():
        for r in stats.get(eid, []):
            if r.get("mean") is not None:
                by_t[_ts(r["start"])][role] = float(r["mean"]) * k[role] * (sign if role == "grid" else 1.0)
    if not by_t:
        return None
    samples = []
    for t in sorted(by_t):
        v, loc = by_t[t], dt_util.as_local(datetime.fromtimestamp(t, tz=timezone.utc))
        samples.append(battery.Sample(t, loc.date().isoformat(), loc.hour, v.get("battery"), v.get("grid"), v.get("pv"), v.get("soc")))
    cap = conf.get(CONF_BATTERY_KWH)
    return await hass.async_add_executor_job(battery.learn, samples, float(cap) if cap else None)


async def async_rows(mgr: "RoostManager") -> tuple[list, dict]:
    hass = mgr.hass
    end = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=HISTORY_DAYS)
    if mgr._pump_hours:
        start = min(start, datetime.fromtimestamp(min(mgr._pump_hours), tz=timezone.utc))
    conf = mgr.conf
    ids: dict[str, str] = {}
    if conf.get(CONF_ROOM):
        ids["room"] = conf[CONF_ROOM]
    for role in ("thermostat_room", "thermostat_setpoint", "outdoor", *ENERGY_ROLES):
        if mgr.ent.get(role):
            ids[role] = mgr.ent[role]
    if conf.get(CONF_PV_POWER):
        ids["pv"] = conf[CONF_PV_POWER]
    if conf.get(CONF_HOUSE_POWER):
        ids["house"] = conf[CONF_HOUSE_POWER]
    elif _derive_house(conf):
        ids["grid"] = conf[CONF_GRID_POWER]
        if conf.get(CONF_BATTERY_POWER):
            ids["battery"] = conf[CONF_BATTERY_POWER]
    stats = await get_instance(hass).async_add_executor_job(
        statistics.statistics_during_period, hass, start, end, set(ids.values()), "hour", None, {"mean", "change"})

    ha: dict[int, dict] = defaultdict(dict)
    for role, eid in ids.items():
        for r in stats.get(eid, []):
            t = _ts(r["start"])
            v = r.get("change") if role in ENERGY_ROLES else r.get("mean")
            if v is not None:
                ha[t][role] = float(v)
    for t, v in ha.items():
        if "heat" in v:
            v["q"] = v["heat"] + v.get("heat_defrost", 0.0)
        if "elec" in v:
            v["e"] = v["elec"] + v.get("elec_defrost", 0.0)
        if "elec_dhw" in v:
            v["dhw_e"] = v["elec_dhw"]
        if "outdoor" in v:
            v["sensor_out"] = v["outdoor"]
        if "thermostat_setpoint" in v and history.BAD_LOW < v["thermostat_setpoint"] < history.BAD_HIGH:
            v["sp"] = v["thermostat_setpoint"]
        if "room" in v and not (history.BAD_LOW < v["room"] < history.BAD_HIGH):
            del v["room"]

    # weather: the forecast service keeps ~3 months of past days, older from the archive (cached)
    recent_from = end - timedelta(days=88)
    if start < recent_from:
        await _async_archive(mgr, start, min(recent_from, end - timedelta(days=5)))
    wx = dict(mgr._weather_hist)
    wx.update(mgr._weather)
    rows = history.build_rows(mgr._pump_hours, dict(ha), wx)

    extra: dict = {}
    pv = [(v["pv"], wx[t][1]) for t, v in ha.items() if "pv" in v and t in wx and wx[t][1] >= 0.3]
    if len(pv) >= 30:
        k = _to_kw(hass, conf[CONF_PV_POWER])
        ratios = sorted(p * k / r for p, r in pv)
        extra["pv_k"] = round(min(50.0, max(0.0, ratios[len(ratios) // 2])), 3)
    house: dict[int, float] = {}            # hour -> kWh the house used, the heat pump included
    if conf.get(CONF_HOUSE_POWER):
        k = _to_kw(hass, conf[CONF_HOUSE_POWER])
        house = {t: v["house"] * k for t, v in ha.items() if "house" in v}
    elif _derive_house(conf):
        kg, kp = _to_kw(hass, conf[CONF_GRID_POWER]), _to_kw(hass, conf[CONF_PV_POWER])
        kb = _to_kw(hass, conf[CONF_BATTERY_POWER]) if conf.get(CONF_BATTERY_POWER) else 1.0
        imp_pos = conf.get(CONF_GRID_SIGN, "import_positive") == "import_positive"
        for t, v in ha.items():
            # many inverters go unavailable at night: no solar reading in a dark hour is no solar
            pv_kw = v["pv"] * kp if "pv" in v else (0.0 if t in wx and wx[t][1] < 0.005 else None)
            if "grid" in v and pv_kw is not None and ("battery" in v or "battery" not in ids):
                house[t] = value.house_use(v["grid"] * kg, pv_kw, v["battery"] * kb if "battery" in v else None, imp_pos)
    if house:
        per: dict[int, list[float]] = defaultdict(list)
        for t, kwh in house.items():
            if t >= end.timestamp() - 21 * 86400:
                hp = mgr._pump_hours.get(t, {})      # the Quatt has no energy meter: its hours from the statistics
                hp_kwh = ha[t].get("e", hp.get("e", 0.0)) + ha[t].get("dhw_e", hp.get("dhw_e", 0.0))
                per[dt_util.as_local(datetime.fromtimestamp(t, tz=timezone.utc)).hour].append(max(0.0, kwh - hp_kwh))
        if len(per) == 24 and all(len(x) >= 3 for x in per.values()):
            extra["load_profile"] = [round(sorted(per[h])[len(per[h]) // 2], 3) for h in range(24)]
    return rows, extra
