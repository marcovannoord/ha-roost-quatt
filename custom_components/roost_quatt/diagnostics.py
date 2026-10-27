"""Diagnostics download for a bug report: everything needed to see what happened and to replay the plan.

Settings, versions, the state of every entity Roost reads, the learned models, the self-check, the inputs and the result
of the current plan, the last hours, what Roost did and why (its event log), and its last warnings and errors. Roost keeps
no passwords or tokens; the home location is left out.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from . import RoostConfigEntry, recent_log
from .const import DOMAIN
from .quatt import QUATT
from .manager import HOUR_LOG_KEPT, PLAN_LOG_KEPT

REDACT = {"lat", "lon", "latitude", "longitude", "access_token", "refresh_token", "token"}


def _state(hass: HomeAssistant, entity_id: str | None) -> dict | None:
    st = hass.states.get(entity_id) if entity_id else None
    if st is None:
        return {"entity_id": entity_id, "state": "missing"} if entity_id else None
    a = st.attributes
    out = {"entity_id": entity_id, "state": st.state, "unit": a.get("unit_of_measurement"), "device_class": a.get("device_class"),
           "last_updated": st.last_updated.isoformat(), "attributes": sorted(a.keys())[:40]}
    if entity_id.startswith("climate."):
        out.update({k: a.get(k) for k in ("temperature", "current_temperature", "hvac_action", "hvac_modes", "min_temp", "max_temp")})
    return out


async def _version(hass: HomeAssistant, domain: str) -> str | None:
    try:
        integ = await async_get_integration(hass, domain)
    except Exception:  # noqa: BLE001
        return None
    return "built-in" if integ.is_built_in else str(integ.version)


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: RoostConfigEntry) -> dict[str, Any]:
    m = entry.runtime_data
    p = m.plan
    conf = m.conf
    entity_ids = sorted({v for k, v in conf.items() if isinstance(v, str) and "." in v and k != "name"} | set(m.ent.values())
                        | {r.sensor for r in m.rooms})
    data = {
        "versions": {"roost_quatt": await _version(hass, DOMAIN), "home_assistant": HA_VERSION, "quatt": await _version(hass, "quatt")},
        "settings": conf, "mode": m.mode, "heat_pump": m.pump_name, "quatt_entities": m.ent,
        "quatt_roles_missing": sorted(set(QUATT) - set(m.ent)),
        "entities": [_state(hass, e) for e in entity_ids],
        "now": {"room": m.room(), "thermostat_setpoint": m.thermostat_sp(), "thermostat_reading": m.thermostat_reading(),
                "pump_state": m.pump_state(), "storage_kwh": m.storage_e, "following": m.following, "sources": m.sources,
                "reason": m.reason.as_dict(), "decision": m.decision.as_dict() if m.decision else None, "control": m.mem.as_dict(),
                "correction_kw": m.corr_kw, "correction_hours": m.corr_n},
        "models": {"house": m.house.as_dict(), "heat_pump": m.pump.as_dict(),
                   "rooms": {k: v.as_dict() for k, v in m.room_models.items()}, "building": m.building},
        "learning": m.learn_info, "import": m.import_info,
        "heating_curve": m.curve_advice.as_dict() if m.curve_advice else None, "quatt_info": m.quatt_info, "hybrid": m.hybrid, "check": m.check, "ready_to_steer": m.ready, "still_missing": m.ready_missing,
        "plan": {"settings": vars(m.settings()), "control": vars(m.control_settings()),
                 "inputs": [vars(h) for h in m.plan_hours], "hours": [h.as_dict() for h in p.hours] if p else None,
                 "tariff": m.plan_tariff, "tariff_guessed": m.plan_guess,
                 "cost": p.cost if p else None, "steady_cost": p.baseline_cost if p else None, "rooms": m.room_status},
        "hour_log": m.hour_log[-HOUR_LOG_KEPT:], "plan_log": m.plan_log[-PLAN_LOG_KEPT:], "saving_days": m.saving_days, "day_stats": m.day_stats,
        "saving_explained": {"next_24h": m.next_breakdown(), "days": m.saving_detail}, "plan_changes": m.plan_changes,
        "thermostat_history": {str(k): v for k, v in sorted(m.sp_hist.items())[-72:]},
        "rooms": [vars(r) for r in m.rooms], "changes_by_hand": m.changes[-40:],
        "suggestion": m.suggestion.as_dict() if m.suggestion else None, "issues": sorted(m.health.issues),
        "events": list(m.events), "log": list(recent_log(hass).records),
        "pump_hours": len(m._pump_hours), "pump_hours_counted_live": sum(1 for v in m._pump_hours.values() if "heating_s_live" in v), "gas_boiler_hours": m.boiler_hours, "pv_k": m.pv_k, "load_profile": m.load_profile, "battery": m.battery.as_dict(),
    }
    return async_redact_data(data, REDACT)
