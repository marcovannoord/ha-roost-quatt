"""Combine the hourly sources into model rows. Pure Python.

Per hour, each value from the best source that has it:
- heat and electricity for space heating: the Weheat logs (imported) — the unit's own meters, no gaps when Home
  Assistant was off — else Home Assistant's long-term statistics of the Weheat energy sensors;
- seconds per state (heating / hot water / legionella / defrost / manual): the Weheat logs; for a Quatt the seconds of
  heating Roost counted itself from the CIC's state (heating_s_live), else estimated from the statistics
  (quatt.hours_from_stats, which also gives a Quatt's heat and electricity per hour);
- room temperature: the room sensor chosen in Roost (HA statistics), else the thermostat's reading in the Weheat logs,
  else the thermostat's reading in HA;
- the heat pump's outdoor reading: Weheat logs, else HA statistics;
- the room setpoint on the thermostat: Weheat logs (what the unit received), else HA statistics;
- outdoor temperature, radiation and wind: the weather service (forecast with past days, or the archive).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .model import WIND_REF, HourRow

BAD_LOW, BAD_HIGH = 0.5, 95.0          # Weheat reports -1 °C (and other nonsense) when a sensor fails


def _ts(v: Any) -> int | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        x = float(v)
        return int(x / 1000 if x > 1e11 else x)
    if isinstance(v, datetime):
        return int((v if v.tzinfo else v.replace(tzinfo=timezone.utc)).timestamp())
    s = str(v).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _temp(v: Any) -> float | None:
    x = _f(v)
    return x if x is not None and BAD_LOW < x < BAD_HIGH else None


def _outdoor(v: Any) -> float | None:
    x = _f(v)
    return x if x is not None and -45.0 < x < 50.0 and x != -1.0 else None


# Kept per hour for later use, only when not zero or empty (most hours are zero): Roost's key -> the API's field
EXTRA_LOGS = {
    "th_on_s": "thermostatStateOn",                 # seconds the thermostat asked for heat
    "th_water": "tThermostatSetpointAverage",       # water temperature an OpenTherm thermostat asked for
    "heater_s": "controlBridgeStatusElectricHeater",    # seconds the backup electric heater was on
    "boiler_s": "controlBridgeStatusGasBoiler",     # seconds a gas boiler ran (hybrid)
    "boiler_flow": "otBoilerFeedTemperatureAverage",
    "rpm_max": "rpmMax",
    "lim_silent_s": "rpmLimiterSilentHours",        # seconds the compressor was held back, and why
    "lim_power_s": "rpmLimiterPowerLimit",
    "lim_water_s": "rpmLimiterWaterOut",
    "lim_house_s": "rpmLimiterHouseIn",
    "lim_envelope_s": "rpmLimiterEnvelope",
    "err_s": "dtcError",                            # seconds in error, on the fallback curve, compressor blocked
    "fallback_curve_s": "dtcUseHeatingCurve",
    "comp_off_s": "dtcCompressorOff",
    "cooling_s": "heatPumpStateCooling",
    "ch_flow": "centralHeatingFlowAverage",         # water flow rate (l/min)
    "house_ret": "tWaterHouseInAverage",            # water back from the house (buffer, indoor unit)
}
EXTRA_ENERGY = {"standby_e": "totalEInStandby", "dhw_q": "totalEOutDhw"}


def _extras(x: dict, fields: dict[str, str]) -> dict:
    out = {}
    for key, api in fields.items():
        v = _f(x.get(api))
        if v:
            out[key] = round(v, 2)
    return out


BOILER_MIN_S = 300         # a gas boiler that ran at least 5 minutes in an hour
HYBRID_HOURS = 3           # ... in this many hours of the year: a hybrid heat pump


def boiler_hours(hours: dict[int, dict]) -> int:
    """Hours in which the unit asked for a gas boiler (Weheat's hourly logs, controlBridgeStatusGasBoiler; the flag is
    a request: a unit without a boiler sets it now and then too), or a Quatt's boiler gave heat."""
    return sum(1 for v in hours.values() if (v.get("boiler_s") or 0) >= BOILER_MIN_S)


def is_hybrid(boiler_type: int | None, hours_with_boiler: int) -> bool:
    """A gas boiler next to the heat pump. Weheat's boilerType says it (1 none, 2 on/off, 3 OpenTherm); only when that
    is unknown (0, or not read yet) the hours the unit asked for a boiler decide."""
    if boiler_type in (2, 3):
        return True
    if boiler_type == 1:
        return False
    return hours_with_boiler >= HYBRID_HOURS


def merge_hours(have: dict[int, dict], new: dict[int, dict]) -> None:
    """Add hours from Weheat to the ones kept, field by field: reading the hourly logs alone (to add new fields) must
    keep the energy an hour already has."""
    for t, v in new.items():
        have.setdefault(t, {}).update(v)


def weheat_hours(logs: list[dict], energy: list[dict]) -> dict[int, dict]:
    """Weheat hourly logs + energy logs -> {hour ts: {...}} (keys as in the API, camelCase)."""
    out: dict[int, dict] = {}
    for x in logs or []:
        t = _ts(x.get("timeBucket"))
        if t is None:
            continue
        t -= t % 3600
        out.setdefault(t, {}).update({
            "room": _temp(x.get("tRoomAverage")),
            "sp": _temp(x.get("tRoomTargetAverage")),
            "sensor_out": _outdoor(x.get("tAirInAverage")),
            "heating_s": (_f(x.get("heatPumpStateHeating")) or 0.0) + (_f(x.get("heatPumpStateHeatingDefrost")) or 0.0),
            "dhw_s": sum(_f(x.get(k)) or 0.0 for k in ("heatPumpStateDhw", "heatPumpStateLegionella", "heatPumpStateDhwDefrost")),
            "manual_s": _f(x.get("heatPumpStateManualControl")) or 0.0,
            # the water the unit sends to the house and gets back (for the heating curve advice)
            "flow": _temp(x.get("tWaterOutAverage")),
            "ret": _temp(x.get("tWaterInAverage")),
            # kept for later use (modulation, cycling), so that needs no new import
            "rpm": _f(x.get("rpmAverage")), "rpm_min": _f(x.get("rpmMin")),
            **_extras(x, EXTRA_LOGS),
        })
    for x in energy or []:
        t = _ts(x.get("timeBucket"))
        if t is None:
            continue
        t -= t % 3600
        q = (_f(x.get("totalEOutHeating")) or 0.0) + (_f(x.get("totalEOutHeatingDefrost")) or 0.0)
        e = (_f(x.get("totalEInHeating")) or 0.0) + (_f(x.get("totalEInHeatingDefrost")) or 0.0)
        out.setdefault(t, {}).update({"q": max(0.0, q), "e": max(0.0, e),
                                      "dhw_e": (_f(x.get("totalEInDhw")) or 0.0) + (_f(x.get("totalEInDhwDefrost")) or 0.0),
                                      **_extras(x, EXTRA_ENERGY)})
    return out


def build_rows(pump: dict[int, dict], ha: dict[int, dict], weather: dict[int, tuple]) -> list[HourRow]:
    """pump: the unit's hours (weheat_hours, or quatt.hours_from_stats). ha: {hour ts: {"room", "thermostat_room", "sp",
    "q", "e", "dhw_e", "sensor_out"}} from long-term statistics. weather: {hour ts: (t_out, radiation kW/m², wind m/s)}."""
    rows: list[HourRow] = []
    for t in sorted(set(pump) | set(ha)):
        w, h = pump.get(t, {}), ha.get(t, {})
        wx = weather.get(t)
        if wx is None or wx[0] is None:
            continue
        room = h.get("room")
        th = w.get("room") if w.get("room") is not None else h.get("thermostat_room")     # the thermostat's reading
        th = th if th is not None and BAD_LOW < th < BAD_HIGH else None
        sensor = room is not None
        if room is None:
            room = th
        if room is None or not (BAD_LOW < room < BAD_HIGH):
            continue
        if "q" in w:
            q, e, dhw_e = w["q"], w.get("e", 0.0), w.get("dhw_e", 0.0)
        elif h.get("q") is not None:
            q, e, dhw_e = max(0.0, h["q"]), max(0.0, h.get("e") or 0.0), max(0.0, h.get("dhw_e") or 0.0)
        else:
            continue
        if w.get("manual_s", 0.0) > 600:               # someone ran the unit by hand: not normal operation
            continue
        dhw_s = w.get("dhw_s", 3600.0 if dhw_e > 0.05 else 0.0)
        rows.append(HourRow(ts=t, T=room, T_out=wx[0], Q=q, rad=max(0.0, wx[1] or 0.0), wind=wx[2] if wx[2] is not None else WIND_REF,
                            E=e, T_out_sensor=w.get("sensor_out") if w.get("sensor_out") is not None else h.get("sensor_out"),
                            dhw_s=dhw_s, heating_s=w.get("heating_s_live", w.get("heating_s", 0.0)),   # Weheat's logs, or counted (Quatt)
                            sp=w.get("sp") if w.get("sp") is not None else h.get("sp"),
                            T_th=th, room_sensor=sensor))
    return rows
