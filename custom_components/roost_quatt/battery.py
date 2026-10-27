"""How the home battery is used, learned from 5-minute means of its power, the grid meter, solar and its charge. Pure Python.

Whoever steers the battery (Predbat, evcc, a supplier's app, a schedule in the inverter) is not asked: what it does is
measured. All the battery charges beyond the solar left over comes from the grid:
    with a grid meter     grid charging = min(charging, import)        (solar goes to the house first)
    with solar only       grid charging = charging - solar
    no power sensor       charging from the rise of the state of charge × the capacity
5-minute means, not hourly ones: in one hour a battery can charge from solar first and from the grid after.

In an hour in which the battery usually charges from the grid it supplies nothing: extra use comes from the grid at that
hour's price, and the battery is simulated charging to its usual level (value.py). When the user lets the heat pump use
the battery, a kWh taken from it costs the cheapest of those charging hours ahead instead of the hour in which it would
run empty. Only hours with room count for that: after an hour in which it is usually full (median) an extra kWh does not
fit.

A battery whose steering charges it from the grid also discharges it on its own terms (selling in the evening peak, keeping
a charge for the morning): the solar-and-house simulation in value.py does not know that. Its usual charge per hour of the
day (median of the days) is followed instead.

Not every battery covers the house whenever it has charge: some are steered to keep it for the evening peak (issue #5: a
Marstek filled by day, delivering only in the evening). The hours in which it usually keeps its charge while the house
draws from the grid are learned (needs a grid meter and the battery's power): extra use then comes from the grid, at that
hour's price. Hours without enough such moments count as hours it supplies, as before.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

GRID_KW_MIN = 0.3          # a 5-minute mean of grid charging below this is noise (a battery balancing, meter timing)
DAY_KWH_MIN = 0.5          # a day with at least this much grid charging counts as a charging day
MIN_DAYS = 3               # charging days before Roost counts on it
HOUR_SHARE = 0.25          # a local hour is a charging hour when the battery charged from the grid in it on this share of the days
FULL_SOC = 95.0            # charged to this in an hour (median over the days): no room for an extra kWh then
LOW_SOC = 25.0             # a day whose lowest charge is below this ran down to the battery's reserve
NEED_KW = 0.3              # the house draws at least this from the grid and the battery together (5-minute mean)
SUPPLY_KW = 0.1            # the battery delivers at least this: it supplies (also when its power limit is below the need)
ROOM_SOC = 5.0             # with this much above its reserve (or the 10 % default) it could have supplied
HOLD_SHARE = 0.5           # a local hour is a holding hour when it delivered in less than this share of those moments
STEP_H = 5 / 60


@dataclass
class Sample:
    ts: float                      # start of the 5 minutes (epoch)
    day: str                       # local date
    hour: int                      # local hour
    battery_kw: float | None       # + discharging, - charging
    grid_kw: float | None          # + import
    pv_kw: float | None
    soc: float | None              # %


@dataclass
class BatteryHabits:
    days: int = 0                  # days with samples
    grid_days: int = 0             # days on which the battery charged from the grid
    grid_kwh_day: float = 0.0      # grid charging per day, on average
    grid_hours: list[int] = field(default_factory=list)     # local hours in which it charges from the grid
    charge_hours: list[int] = field(default_factory=list)   # ... of those, the ones after which it still has room
    top_soc: dict[str, float] = field(default_factory=dict)  # local hour -> charge reached while charging from the grid (median)
    reserve: float | None = None   # the charge it stops at when it runs down (median), None: not seen
    soc_by_hour: dict[str, float] = field(default_factory=dict)   # local hour -> usual charge at its start (median)
    hold_hours: list[int] = field(default_factory=list)     # local hours in which it keeps its charge though the house needs it
    at: str | None = None

    @property
    def charges_from_grid(self) -> bool:
        return self.grid_days >= MIN_DAYS and bool(self.grid_hours)

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "BatteryHabits":
        m = cls()
        for k, v in (d or {}).items():
            if hasattr(m, k) and not isinstance(getattr(cls, k, None), property):
                setattr(m, k, v)
        return m


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def grid_charge_kw(charge_kw: float, grid_kw: float | None, pv_kw: float | None) -> float:
    """The part of the charging power that comes from the grid (kW)."""
    if charge_kw <= 0:
        return 0.0
    if grid_kw is not None:
        return min(charge_kw, max(0.0, grid_kw))
    if pv_kw is not None:
        return max(0.0, charge_kw - max(0.0, pv_kw))
    return 0.0


def learn(samples: list[Sample], capacity_kwh: float | None = None) -> BatteryHabits:
    """The battery's habits from 5-minute samples (oldest first)."""
    samples = sorted(samples, key=lambda s: s.ts)
    days: dict[str, float] = {}                       # day -> kWh charged from the grid
    hours: dict[int, set[str]] = {}                   # local hour -> days with grid charging in it
    top: dict[tuple[int, str], float] = {}            # (hour, day) -> highest charge while charging from the grid
    low: dict[str, float] = {}                        # day -> lowest charge
    for i, s in enumerate(samples):
        days.setdefault(s.day, 0.0)
        if s.soc is not None:
            low[s.day] = min(low.get(s.day, s.soc), s.soc)
        if s.battery_kw is not None:
            charge = max(0.0, -s.battery_kw)
        elif capacity_kwh and s.soc is not None and i + 1 < len(samples) and samples[i + 1].soc is not None \
                and samples[i + 1].ts - s.ts <= 600:
            charge = max(0.0, (samples[i + 1].soc - s.soc) / 100 * capacity_kwh / ((samples[i + 1].ts - s.ts) / 3600))
        else:
            continue
        g = grid_charge_kw(charge, s.grid_kw, s.pv_kw)
        if g < GRID_KW_MIN:
            continue
        days[s.day] += g * STEP_H
        hours.setdefault(s.hour, set()).add(s.day)
        if s.soc is not None:
            top[(s.hour, s.day)] = max(top.get((s.hour, s.day), s.soc), s.soc)
    charging = [d for d, kwh in days.items() if kwh >= DAY_KWH_MIN]
    n = len(days)
    out = BatteryHabits(days=n, grid_days=len(charging),
                        grid_kwh_day=round(sum(days.values()) / n, 2) if n else 0.0)
    if charging:
        need = max(2, HOUR_SHARE * n)
        for h in sorted(h for h, ds in hours.items() if len(ds & set(charging)) >= need):
            tops = [v for (hh, d), v in top.items() if hh == h and d in charging]
            out.grid_hours.append(h)
            if tops:
                out.top_soc[str(h)] = round(_median(tops), 1)
            if not tops or out.top_soc[str(h)] < FULL_SOC:
                out.charge_hours.append(h)
    at_hour: dict[int, list[float]] = {}
    for s in samples:
        if s.soc is not None and s.ts % 3600 == 0:
            at_hour.setdefault(s.hour, []).append(s.soc)
    if len(at_hour) == 24 and all(len(v) >= MIN_DAYS for v in at_hour.values()):
        out.soc_by_hour = {str(h): round(_median(v), 1) for h, v in sorted(at_hour.items())}
    lows = [v for v in low.values() if v < LOW_SOC]
    if len(lows) >= MIN_DAYS:
        out.reserve = round(_median(lows), 1)
    out.hold_hours = hold_hours(samples, out.reserve)
    return out


def hold_hours(samples: list[Sample], reserve: float | None) -> list[int]:
    """Local hours in which the battery usually keeps its charge although the house draws from the grid: moments with a
    need (grid import + discharge >= NEED_KW), charge to spare and no grid charging; in an hour it delivered in fewer
    than HOLD_SHARE of them, on at least MIN_DAYS days. Without a grid meter or the battery's power: none known."""
    floor = (reserve if reserve is not None else 10.0) + ROOM_SOC
    need: dict[int, int] = {}
    gave: dict[int, int] = {}
    days: dict[int, set[str]] = {}
    for s in samples:
        if s.battery_kw is None or s.grid_kw is None or (s.soc is not None and s.soc <= floor):
            continue
        if s.battery_kw < 0 and grid_charge_kw(-s.battery_kw, s.grid_kw, s.pv_kw) >= GRID_KW_MIN:
            continue                                  # charging from the grid: that hour is a grid hour already
        if max(0.0, s.grid_kw) + max(0.0, s.battery_kw) < NEED_KW:
            continue
        need[s.hour] = need.get(s.hour, 0) + 1
        gave[s.hour] = gave.get(s.hour, 0) + (s.battery_kw >= SUPPLY_KW)
        days.setdefault(s.hour, set()).add(s.day)
    return sorted(h for h, n in need.items() if len(days[h]) >= MIN_DAYS and gave[h] < HOLD_SHARE * n)
