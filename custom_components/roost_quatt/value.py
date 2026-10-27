"""What does one extra kWh cost in each of the coming hours?

Pure Python. The answer depends on where that kWh would come from:

- solar that would otherwise be exported  -> the export price (plus nothing: it is "free" apart from lost feed-in);
- solar that goes into a home battery that fills up today anyway -> the export price as well (the battery is full
  a little later, and that energy would have been exported);
- energy taken from the home battery -> the price at which the battery is refilled: the import price of the hour in
  which the battery would otherwise have run empty, or the export price if solar would have refilled it before that;
  a battery that charges from the grid (learned in battery.py) is refilled in the cheapest of its charging hours
  before that, when that is cheaper (the battery's losses included) and the user lets the heat pump use it;
- an hour in which the battery charges from the grid -> the import price: the battery supplies nothing then;
- an hour in which its steering keeps the charge for later (learned in battery.py) -> the import price as well;
- the grid -> the import price of that hour, plus a small preference for using own energy (configurable).

Only real solar counts as own solar: export minus battery discharge, never more than the PV power (a battery
that is selling to the grid is not solar; learned on 14-10-2026 in the author's Node-RED controller).

With a Predbat marginal-cost table available and switched on, that table can replace the estimate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SOURCE_SOLAR = "solar"
SOURCE_BATTERY = "battery"
SOURCE_GRID = "grid"
SOURCE_PREDBAT = "predbat"


@dataclass
class EnergyInputs:
    import_price: list[float]                     # per hour, currency/kWh (hour 0 = now)
    export_price: list[float] | None = None       # None: same as import (net metering)
    pv_kwh: list[float] | None = None             # expected solar per hour
    load_kwh: list[float] | None = None           # expected house use per hour without the heat pump
    surplus_now_kw: float = 0.0                   # measured, sustained export right now
    battery_soc: float | None = None              # %
    battery_kwh: float | None = None              # usable capacity
    battery_reserve: float = 10.0                 # %
    battery_max_kw: float = 5.0
    battery_efficiency: float = 0.9               # round trip
    grid_preference: float = 0.0                  # added to grid hours (prefer own energy)
    predbat: list[float | None] | None = None     # optional marginal costs per hour
    grid_charge: list[bool] | None = None         # per hour: cheap refill hour (charges from the grid, with room)
    grid_charge_to: list[float | None] | None = None   # per hour: the charge (%) it is usually brought to from the grid
    soc_usual: list[float | None] | None = None   # per hour: the charge (%) it usually has at the end (a steered battery)
    battery_holds: list[bool] | None = None       # per hour: it keeps its charge though the house needs it (a steered battery)


@dataclass
class EnergyValue:
    value: list[float]                            # currency per kWh per hour
    source: list[str]
    surplus_kwh: list[float] = field(default_factory=list)
    battery_soc: list[float | None] = field(default_factory=list)

    def summary(self) -> dict:
        return {"value": [round(v, 4) for v in self.value], "source": self.source,
                "surplus_kwh": [round(v, 2) for v in self.surplus_kwh],
                "battery_soc": [None if s is None else round(s, 1) for s in self.battery_soc]}


def compute(inp: EnergyInputs) -> EnergyValue:
    n = len(inp.import_price)
    imp = list(inp.import_price)
    exp = list(inp.export_price) if inp.export_price else list(imp)
    exp = (exp + [exp[-1] if exp else 0.0] * n)[:n]
    pv = (list(inp.pv_kwh or []) + [0.0] * n)[:n]
    load = (list(inp.load_kwh or []) + [0.4] * n)[:n]

    # 1. simulate the battery hour by hour with the expected solar and house use
    has_bat = inp.battery_soc is not None and inp.battery_kwh
    cap = float(inp.battery_kwh or 0.0)
    e_res = cap * inp.battery_reserve / 100
    e = cap * (inp.battery_soc or 0) / 100 if has_bat else 0.0
    soc_path: list[float | None] = []
    spill = [0.0] * n                  # solar exported per hour (battery full or absent)
    full_at = [False] * n              # battery at the top at the end of the hour
    empty_at = [False] * n             # battery at the reserve at the end of the hour
    to = (list(inp.grid_charge_to or []) + [None] * n)[:n]
    usual = (list(inp.soc_usual or []) + [None] * n)[:n]
    holds = (list(inp.battery_holds or []) + [False] * n)[:n]
    charging = [False] * n            # the battery charges this hour: it supplies nothing
    for h in range(n):
        net = pv[h] - load[h]          # >0: surplus, <0: shortage
        if h == 0 and inp.surplus_now_kw > 0:
            net = max(net, inp.surplus_now_kw)
        if has_bat:
            before = e
            if net > 0:
                take = min(net, inp.battery_max_kw, cap - e)
                e += take
                spill[h] = net - take
            elif to[h] is None and not holds[h]:
                give = min(-net, inp.battery_max_kw, e - e_res)
                e -= max(0.0, give)
            if to[h] is not None:      # charging from the grid: up to its usual level, the house from the grid meanwhile
                e = max(e, min(cap, e + inp.battery_max_kw, cap * to[h] / 100))
            if usual[h] is not None:   # a steered battery: the charge it usually has then (battery.py)
                e = cap * min(100.0, max(0.0, usual[h])) / 100
            charging[h] = to[h] is not None or (usual[h] is not None and e > before + 0.01 * cap)
            full_at[h] = e >= cap - 0.05
            empty_at[h] = e <= e_res + 0.05
            soc_path.append(100 * e / cap)
        else:
            spill[h] = max(0.0, net)
            soc_path.append(None)

    # 2. marginal value per hour
    netlist = [pv[k] - load[k] for k in range(n)]
    val: list[float] = []
    src: list[str] = []
    for h in range(n):
        surplus = max(0.0, pv[h] - load[h])
        if h == 0:
            surplus = max(surplus, inp.surplus_now_kw)
        if spill[h] >= 1.0 or (h == 0 and inp.surplus_now_kw >= 1.0):
            v, s = exp[h], SOURCE_SOLAR
        elif has_bat and surplus > 0 and _fills_later_today(full_at, spill, netlist, h):
            v, s = exp[h], SOURCE_SOLAR                       # the battery fills anyway: extra use only delays that
        elif spill[h] > 0:
            f = min(1.0, spill[h])                            # part of the extra kWh is surplus, the rest grid
            v, s = f * exp[h] + (1 - f) * (imp[h] + inp.grid_preference), SOURCE_SOLAR
        elif has_bat and charging[h]:
            v, s = imp[h] + inp.grid_preference, SOURCE_GRID      # the battery charges: supplies nothing
        elif has_bat and not holds[h] and not empty_at[h] and soc_path[h] is not None and soc_path[h] > inp.battery_reserve + 2:
            v, s = _refill_cost(h, n, imp, exp, spill, empty_at, inp), SOURCE_BATTERY
        else:
            v, s = imp[h] + inp.grid_preference, SOURCE_GRID
        if inp.predbat and h < len(inp.predbat) and inp.predbat[h] is not None:
            v, s = float(inp.predbat[h]), SOURCE_PREDBAT
        val.append(v)
        src.append(s)
    return EnergyValue(val, src, spill, soc_path)


def _fills_later_today(full_at: list[bool], spill: list[float], net: list[float], h: int) -> bool:
    """The battery reaches full and starts exporting before this run of solar surplus ends."""
    for k in range(h, len(full_at)):
        if net[k] <= 0:
            return False
        if full_at[k] and spill[k] > 0.05:
            return True
    return False


def _refill_cost(h: int, n: int, imp: list[float], exp: list[float], spill: list[float], empty_at: list[bool],
                 inp: EnergyInputs) -> float:
    """A kWh taken from the battery now is missing later: bought when the battery would run empty, or not missed at
    all when solar refills it to full first (then it would have been exported). A battery that charges from the grid
    takes it in one of its charging hours before that instead, when that is cheaper."""
    cost, end = None, n - 1
    for k in range(h + 1, n):
        if spill[k] > 0.05:
            cost, end = exp[k] / inp.battery_efficiency, k
            break
        if empty_at[k]:
            cost, end = imp[k] / inp.battery_efficiency + inp.grid_preference, k
            break
    if cost is None:                    # nothing happens within the horizon: assume the cheapest import hour ahead
        rest = imp[h + 1:] or [imp[h]]
        cost = min(rest) / inp.battery_efficiency + inp.grid_preference
    # Charging hours from the next hour on, also before h: whoever charges from the grid plans that charge for the
    # use it expects (not hour 0: that charge is under way or past).
    gc = inp.grid_charge or []
    grid = [imp[k] for k in range(1, end + 1) if k < len(gc) and gc[k] and k != h]
    if grid:
        cost = min(cost, min(grid) / inp.battery_efficiency + inp.grid_preference)
    return cost


def cheap_or_solar(ev: EnergyValue, hours_ahead: int = 8, factor: float = 0.9) -> bool:
    """For the safety layer: is now a good moment (own solar, or the cheapest of the coming hours and below average)?"""
    if not ev.value:
        return False
    if ev.source[0] == SOURCE_SOLAR:
        return True
    window = ev.value[:max(2, hours_ahead)]
    avg = sum(window) / len(window)
    return ev.value[0] <= min(window[1:]) + 0.01 and ev.value[0] <= avg * factor


@dataclass
class HourPrices:
    p_grid: float          # currency per kWh beyond own solar (grid, or battery at its refill cost)
    p_own: float           # currency per kWh of own solar (what exporting it would earn)
    own_kw: float          # own solar available for extra use this hour (kW)
    source: str


def fixed_prices(hours: list[tuple[int, int]], normal: float, low: float | None = None, low_from: int = 23, low_to: int = 7,
                 low_weekend: bool = True) -> list[float]:
    """A fixed contract per local hour ((weekday 0 = Monday, hour)): the low rate in the low hours (low_from until
    low_to, through midnight when low_from > low_to) and, if chosen, all weekend; else the normal rate."""
    out = []
    for wd, h in hours:
        if low is None:
            out.append(normal)
            continue
        night = (low_from <= h or h < low_to) if low_from > low_to else (low_from <= h < low_to)
        out.append(low if night or (low_weekend and wd >= 5) else normal)
    return out


def planner_prices(inp: EnergyInputs, ev: EnergyValue) -> list[HourPrices]:
    """Split each hour for the heat-pump planner: up to `own_kw` at the solar value, the rest at the grid value."""
    n = len(ev.value)
    exp = list(inp.export_price) if inp.export_price else list(inp.import_price)
    exp = (exp + [exp[-1] if exp else 0.0] * n)[:n]
    out = []
    for h in range(n):
        own = ev.surplus_kwh[h] if h < len(ev.surplus_kwh) else 0.0
        if h == 0:
            own = max(own, inp.surplus_now_kw)
        if ev.source[h] == SOURCE_SOLAR and own < 0.5:
            own = max(own, 1.0)                 # the battery fills anyway: solar going into it is free to use
        grid = ev.value[h] if ev.source[h] in (SOURCE_BATTERY, SOURCE_GRID, SOURCE_PREDBAT) else inp.import_price[h] + inp.grid_preference
        out.append(HourPrices(grid, exp[h], own, ev.source[h]))
    return out


def house_use(grid_kw: float, pv_kw: float | None, battery_kw: float | None, import_positive: bool = True) -> float:
    """What the house uses (kW, the heat pump included) from the grid meter, solar and battery (+ discharging): for
    the usage profile when there is no sensor for the house itself."""
    imp = grid_kw if import_positive else -grid_kw
    return max(0.0, imp + (pv_kw or 0.0) + (battery_kw or 0.0))


def source_split(hp_kw: float, house_kw: float, pv_kw: float, battery_kw: float) -> tuple[float, float, float]:
    """Where the heat pump's power comes from now (kW from own solar, the battery, the grid), in the same mix as the
    whole house: solar first, then the battery discharging, the rest from the grid."""
    if hp_kw <= 0:
        return 0.0, 0.0, 0.0
    house = max(house_kw, hp_kw)
    sun = min(max(0.0, pv_kw), house)
    bat = min(max(0.0, battery_kw), house - sun)
    return hp_kw * sun / house, hp_kw * bat / house, hp_kw * (house - sun - bat) / house


def solar_export_now(grid_kw: float | None, battery_kw: float | None, pv_kw: float | None, import_positive: bool = True) -> float:
    """Solar going to the grid right now (kW): export minus battery discharge, at most the PV power."""
    if grid_kw is None:
        return 0.0
    export = -grid_kw if import_positive else grid_kw
    export -= max(0.0, battery_kw or 0.0)
    if pv_kw is not None:
        export = min(export, pv_kw)
    return max(0.0, export)
