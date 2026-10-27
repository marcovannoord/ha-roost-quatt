"""Combine the hourly sources into model rows. Pure Python.

Per hour, each value from the best source that has it:
- heat and electricity for space heating: the heat pump's hours (quatt.hours_from_stats: the hourly means of the
  Quatt power sensors in Home Assistant's long-term statistics);
- seconds of space heating: counted by Roost from the CIC's state (heating_s_live), else estimated from the statistics;
- room temperature: the room sensor chosen in Roost (HA statistics), else the thermostat's reading as the CIC got it
  over OpenTherm, else the thermostat's reading in HA;
- the heat pump's outdoor reading: the unit's own sensor;
- the room setpoint on the thermostat: what the CIC got over OpenTherm, else HA statistics;
- outdoor temperature, radiation and wind: the weather service (forecast with past days, or the archive).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .model import WIND_REF, HourRow

BAD_LOW, BAD_HIGH = 0.5, 95.0          # a failed sensor reports -1 °C, 0 or nonsense


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



BOILER_MIN_S = 300         # a gas boiler that ran at least 5 minutes in an hour
HYBRID_HOURS = 3           # ... in this many hours of the year: a hybrid heat pump


def boiler_hours(hours: dict[int, dict]) -> int:
    """Hours in which a gas boiler ran next to the heat pump (from the CIC's boiler heat, or its state)."""
    return sum(1 for v in hours.values() if (v.get("boiler_s") or 0) >= BOILER_MIN_S)


def is_hybrid(boiler_type: int | None, hours_with_boiler: int) -> bool:
    """A gas boiler next to the heat pump. boiler_type: 1 none, 2 on/off, 3 OpenTherm, None unknown: then the hours a
    boiler ran decide (a Quatt hybrid whose boiler was removed is all-electric)."""
    if boiler_type in (2, 3):
        return True
    if boiler_type == 1:
        return False
    return hours_with_boiler >= HYBRID_HOURS


def build_rows(pump: dict[int, dict], ha: dict[int, dict], weather: dict[int, tuple]) -> list[HourRow]:
    """ha: {hour ts: {"room", "thermostat_room", "sp", "q", "e", "dhw_e", "sensor_out"}} from long-term statistics.
    weather: {hour ts: (t_out, radiation kW/m², wind m/s)}."""
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
                            dhw_s=dhw_s, heating_s=w.get("heating_s_live", w.get("heating_s", 0.0)),
                            sp=w.get("sp") if w.get("sp") is not None else h.get("sp"),
                            T_th=th, room_sensor=sensor))
    return rows
