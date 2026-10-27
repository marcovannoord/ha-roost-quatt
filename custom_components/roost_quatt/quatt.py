"""Quatt: which entities of the Quatt integration (home-assistant-quatt) Roost reads, what the CIC's state means, and the
heat pump's hours rebuilt from Home Assistant's long-term statistics of those entities. Pure Python.

The Quatt CIC has no energy meters, only power: the heat it delivers (flow rate × the water's temperature rise, or what
the outdoor units report) and the electricity they take. Home Assistant keeps an hourly mean, minimum and maximum of
each for as long as the recorder keeps statistics (forever, by default), so the mean of an hour in kW is that hour's
energy in kWh. That is the year of history Roost learns from, without a login of its own.

Seconds of space heating per hour are estimated from the electricity the units took: an hour
whose lowest reading stayed above RUN_KW ran the whole hour; otherwise the mean against the highest reading gives the
share it ran. From the moment Roost runs it counts the seconds itself from the CIC's state ("heating_s_live").

A Quatt Duo has two outdoor units in series: the second one's outlet is the water that goes to the house.
"""
from __future__ import annotations

from collections.abc import Iterable

# role -> keys of the Quatt integration, first found wins; an entity's unique_id ends in ":<key>"
# (the integration builds it as "<hub>:<device>:<key>")
QUATT: dict[str, tuple[str, ...]] = {
    "state": ("qc.supervisoryControlMode",),
    "power_out": ("computedHeatPower", "computedPower"),     # heat to the house (W): measured flow × ΔT, else reported
    "power_out_hp": ("computedPower",),                      # heat the outdoor units report themselves (W)
    "power_in": ("computedPowerInput",),                     # electricity of all outdoor units (W)
    "power_in_hp1": ("hp1.powerInput",),
    "power_in_hp2": ("hp2.powerInput",),                     # only a Duo has it
    "outdoor": ("hp1.temperatureOutside", "temperatureOutside"),
    "cop": ("computedQuattCop", "computedCop"),
    "thermostat_room": ("thermostat.otFtRoomTemperature",),
    "thermostat_setpoint": ("thermostat.otFtRoomSetpoint",),
    "water_setpoint": ("thermostat.otFtControlSetpoint",),   # the water temperature the OpenTherm thermostat asks for
    "water_out": ("flowMeter.waterSupplyTemperature", "hp2.temperatureWaterOut", "hp1.temperatureWaterOut"),
    "water_in": ("hp1.temperatureWaterIn",),
    "flow_rate": ("qc.flowRateFiltered",),
    "boiler_power": ("boiler.computedBoilerHeatPower", "boilerPower"),
    "units": ("numberOfHeatPumps",),                         # remote API (optional)
}
REQUIRED = ("state", "power_out", "power_in")                # without these Roost cannot follow the heat pump

# what Roost reads from the statistics per hour: role -> statistic types
STAT_ROLES = {
    "power_out": ("mean",), "power_in": ("mean", "min", "max"), "water_out": ("mean",), "water_in": ("mean",),
    "water_setpoint": ("mean", "max"), "thermostat_room": ("mean",), "thermostat_setpoint": ("mean",),
    "outdoor": ("mean",), "boiler_power": ("mean", "max"),
}

# qc.supervisoryControlMode (home-assistant-quatt const.SupervisoryControlMode)
STANDBY_CODES = {0, 1}
HEATING_CODES = {2, 3}                       # heat pump on (3: with the boiler)
BOILER_CODES = {3, 4, 96}                    # a gas boiler on
COOLING_CODES = {5, 6}
FAULT_CODES = {99, 400}
TEXT_STATES = {"standby": 0, "standby - heating": 1, "heating - heatpump only": 2, "heating - heatpump + boiler": 3,
               "heating - boiler only": 4, "chill circulation": 5, "chill cooling": 6}

RUN_KW = 0.15                                # an outdoor unit taking more than this is running (standby is ~10-20 W)
OT_DEMAND_MIN = 15.0                         # a control setpoint above this: the thermostat asks for heat
BOILER_KW = 0.3                              # heat from a gas boiler above this: it ran
BAD_LOW, BAD_HIGH = 0.5, 95.0


def key_of(unique_id: str | None) -> str | None:
    """The Quatt key at the end of a unique_id ("<hub>:<device>:<key>")."""
    if not unique_id or ":" not in unique_id:
        return None
    return unique_id.rsplit(":", 1)[1]


def resolve(entities: Iterable[tuple[str | None, str]]) -> dict[str, str]:
    """(unique_id, entity_id) of the Quatt integration's entities -> {role: entity_id}."""
    by_key: dict[str, str] = {}
    for uid, eid in entities:
        k = key_of(uid)
        if k and k not in by_key:
            by_key[k] = eid
    out = {}
    for role, keys in QUATT.items():
        for k in keys:
            if k in by_key:
                out[role] = by_key[k]
                break
    return out


def is_quatt(roles: dict[str, str]) -> bool:
    return all(r in roles for r in REQUIRED)


def units(roles: dict[str, str], reported: float | None = None) -> int:
    """Outdoor units: what the remote API says, else 2 when the second unit's sensors exist."""
    if reported is not None and reported >= 1:
        return int(reported)
    return 2 if "power_in_hp2" in roles else 1


def code(state: str | None) -> int | None:
    """The CIC's supervisory control mode as a number (the sensor gives the code; the text version as a fallback)."""
    if state is None:
        return None
    s = str(state).strip()
    try:
        return int(float(s))
    except ValueError:
        return TEXT_STATES.get(s.lower())


def pump_state(state: str | None, power_in_kw: float | None = None) -> str | None:
    """Roost's words for what the unit does: heating | standby | boiler | cooling | fault | other (None: unknown).
    Heating needs the units running too: the CIC says 'heating' while it waits for a unit to start."""
    c = code(state)
    if c is None:
        return None
    if c in HEATING_CODES:
        return "heating" if power_in_kw is None or power_in_kw > RUN_KW else "standby"
    if c in STANDBY_CODES:
        return "standby"
    if c in BOILER_CODES:
        return "boiler"
    if c in COOLING_CODES:
        return "cooling"
    if c in FAULT_CODES:
        return "fault"
    return "other"


def heating_seconds(mean_kw: float | None, min_kw: float | None, max_kw: float | None) -> float | None:
    """Seconds the units ran in an hour, from the hourly mean / min / max of their electricity (kW)."""
    if mean_kw is None:
        return None
    if max_kw is None:
        return 3600.0 if mean_kw > RUN_KW else 0.0
    if max_kw <= RUN_KW:
        return 0.0
    if min_kw is not None and min_kw > RUN_KW:
        return 3600.0                                   # never stopped
    # it ran part of the hour at about its highest reading (a little lower: it modulates)
    return round(max(0.0, min(3600.0, 3600.0 * mean_kw / (0.85 * max_kw))), 0)


def _temp(v: float | None) -> float | None:
    return v if v is not None and BAD_LOW < v < BAD_HIGH else None


def _outdoor(v: float | None) -> float | None:
    return v if v is not None and -45.0 < v < 50.0 else None


STANDBY_MIN_HOURS = 24      # hours standing still all hour needed to measure the standby


def standby_kw(pin: dict[int, dict], k: float = 1.0) -> float | None:
    """What the outdoor units take while they stand still (kW): the median of the hours they did not run at all."""
    idle = sorted(v["mean"] * k for v in pin.values()
                  if v.get("mean") is not None and v.get("max") is not None and v["max"] * k <= RUN_KW)
    return round(idle[len(idle) // 2], 4) if len(idle) >= STANDBY_MIN_HOURS else None


def hours_from_stats(stats: dict[str, dict[int, dict]], kw: dict[str, float], standby: float | None = None) -> dict[int, dict]:
    """Long-term statistics per role ({role: {hour ts: {"mean", "min", "max"}}}) and the factor to kW per power role (1: in kW already)
    -> {hour ts: {...}} with the keys history.build_rows reads (q, e, heating_s, flow, ...). standby: what the units take
    standing still (kW), as measured over a longer time (standby_kw); taken out of the electricity."""
    out: dict[int, dict] = {}
    pin, pout = stats.get("power_in") or {}, stats.get("power_out") or {}
    k_in, k_out = kw.get("power_in", 1.0), kw.get("power_out", 1.0)
    if standby is None:                                 # not known yet: measured from these hours (0 when too few)
        standby = standby_kw(pin, k_in) or 0.0
    for t in sorted(set(pin) | set(pout)):
        i, o = pin.get(t) or {}, pout.get(t) or {}
        if i.get("mean") is None or o.get("mean") is None:
            continue                                    # both or nothing: an hour with half the energy misleads
        e, q = max(0.0, i["mean"] * k_in), max(0.0, o["mean"] * k_out)
        secs = heating_seconds(e, i["min"] * k_in if i.get("min") is not None else None,
                               i["max"] * k_in if i.get("max") is not None else None) or 0.0
        # electricity for heating only, as a heat pump's own meter counts it: without the standby of the time it did not run
        idle = standby * (3600.0 - secs) / 3600.0
        h = {"q": round(q, 4), "e": round(max(0.0, e - idle), 4), "dhw_e": 0.0, "dhw_s": 0.0, "heating_s": secs}
        if idle > 0:
            h["standby_e"] = round(min(e, idle), 4)
        out[t] = h
    for t, h in out.items():
        def mean(role: str) -> float | None:
            return ((stats.get(role) or {}).get(t) or {}).get("mean")
        flow, ret = _temp(mean("water_out")), _temp(mean("water_in"))
        if flow is not None and h["heating_s"] > 0:
            h["flow"] = round(flow, 2)
        if ret is not None and h["heating_s"] > 0:
            h["ret"] = round(ret, 2)
        ws = (stats.get("water_setpoint") or {}).get(t) or {}
        if ws.get("max") is not None and ws["max"] > OT_DEMAND_MIN:
            h["th_water"] = round(ws.get("mean") or ws["max"], 1)       # an OpenTherm thermostat asked for water
        room, sp, out_t = _temp(mean("thermostat_room")), _temp(mean("thermostat_setpoint")), _outdoor(mean("outdoor"))
        if room is not None:
            h["room"] = round(room, 2)
        if sp is not None:
            h["sp"] = round(sp, 2)
        if out_t is not None:
            h["sensor_out"] = round(out_t, 1)
        b = (stats.get("boiler_power") or {}).get(t) or {}
        kb = kw.get("boiler_power", 1.0)
        if b.get("max") is not None and b["max"] * kb > BOILER_KW:
            h["boiler_s"] = round(min(3600.0, 3600.0 * (b.get("mean") or 0.0) / b["max"]), 0)
    return out


def merge_hours(have: dict[int, dict], new: dict[int, dict]) -> None:
    """Add hours from the statistics to the ones kept, field by field; what Roost counted itself stays."""
    for t, v in new.items():
        have.setdefault(t, {}).update(v)


class LiveHour:
    """Seconds per state in the current hour, counted from the CIC (more exact than the estimate from statistics)."""

    def __init__(self) -> None:
        self.hour: int | None = None
        self.heating_s = 0.0
        self.boiler_s = 0.0
        self.seen_s = 0.0

    def feed(self, t: float, dt: float, state: str | None) -> tuple[int, dict] | None:
        """One tick: dt seconds in `state`. Returns (hour ts, fields) when an hour closed with most of it seen."""
        hour = int(t // 3600 * 3600)
        closed = None
        if self.hour is not None and hour != self.hour:
            if self.seen_s >= 3000:
                closed = (self.hour, {"heating_s_live": round(min(3600.0, self.heating_s * 3600 / self.seen_s)),
                                      **({"boiler_s": round(self.boiler_s * 3600 / self.seen_s)} if self.boiler_s else {})})
            self.heating_s = self.boiler_s = self.seen_s = 0.0
        self.hour = hour
        if state is not None and dt > 0:
            self.seen_s += dt
            if state == "heating":
                self.heating_s += dt
            elif state == "boiler":
                self.boiler_s += dt
        return closed
