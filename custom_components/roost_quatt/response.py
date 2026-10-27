"""How the heat pump responds to the thermostat, and when it makes hot water. Pure Python.

Roost steers only through the room setpoint, so the planner has to know what the unit does with it. An OpenTherm
thermostat modulates: it asks for about the house's loss plus a gain per degree its own reading is below the setpoint,
and the unit follows with a delay (heatpump.HeatPumpModel.demand). On the author's Lyric T6 + Blackbird P80 (winter
2025/26) the unit still delivered about 70 % of the loss with the room a degree above the setpoint, and about 1 kW
more per degree below it, reaching it over 2–3 hours — far from a thermostat that switches on and off.

Learned from the heat pump's hours (setpoint, the thermostat's reading, heat per hour):
- th_diff       the thermostat's reading minus the room sensor (median, hours with both);
- a, k, offset, follow fitted on 6-hour windows: from the heat measured in the hour before, the output follows the
                demand hour by hour; the error is the mean heat over the window (single hours are noise: the unit
                runs in cycles longer than an hour);
- q_min         lowest steady output: the low end of the output in hours with heating the whole hour;
- cyc           COP while cycling (hours with heating part of the hour) against the COP model at the same output;
- hot water     share of each hour of the week spent on hot water (schedule, legionella), from the last weeks.

A new response is only taken when it predicts the newest fifth of the windows better than the previous one.
Since Roost steers, the newest days may show a unit that answers a setpoint step quite differently from the year of
the thermostat's own steady schedule (a Tado on OpenTherm gave 1.6× the heat learned from that year, and the planner
overheated the house). A second fit on the last RECENT_DAYS alone competes then: fitted without the newest RECENT_MIN
windows and taken only when it predicts those clearly better (RECENT_MARGIN).
"""
from __future__ import annotations

from .heatpump import HeatPumpModel
from .model import WIND_REF, HouseModel, HourRow, unfollowed

WINDOW = 6
MIN_WINDOWS = 100           # usable windows before the response is learned
HEATING_DAY_KWH = 3.0       # only days the unit heated at all (heating off in summer says nothing about the response)
MAX_WINDOWS = 2500          # newest windows used (keeps the nightly run to a few seconds)
T_OUT_MAX = 15.0            # above this the unit hardly heats: those hours say little about the response
MARGIN = 0.02               # a new response must predict at least 2 % better
RECENT_DAYS = 7             # the last days: what the unit does now that Roost steers
RECENT_MIN = 24             # usable windows in those days before they count
RECENT_MARGIN = 0.20        # the recent fit must predict the held-out windows at least 20 % better
GRID = {
    "follow": (1.0, 0.7, 0.5, 0.35, 0.25, 0.15),
    "a": tuple(round(0.6 + 0.1 * i, 1) for i in range(9)),
    "k": (0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0),
    "offset": tuple(round(-1.5 + 0.1 * i, 1) for i in range(31)),
}


def th_diff(rows: list[HourRow]) -> float | None:
    xs = sorted(r.T_th - r.T for r in rows if r.room_sensor and r.T_th is not None and abs(r.T_th - r.T) < 4.0)
    return round(xs[len(xs) // 2], 2) if len(xs) >= 48 else None


def windows(rows: list[HourRow], house: HouseModel, hp: HeatPumpModel) -> list[tuple[float, list[tuple], int]]:
    """Per window: (heat measured in the hour before, [(net loss, setpoint − thermostat reading, hot water share,
    max output, measured heat) per hour], start). Oldest first."""
    idx = {r.ts: r for r in rows}
    unf = unfollowed(rows, house, hp)
    per_day: dict[int, float] = {}
    for r in rows:
        per_day[r.ts // 86400] = per_day.get(r.ts // 86400, 0.0) + r.Q
    out = []
    for t in sorted(idx):
        before = idx.get(t - 3600)
        hrs = [idx.get(t + 3600 * j) for j in range(WINDOW)]
        if before is None or any(r is None or r.sp is None for r in hrs):
            continue
        if any(t + 3600 * j in unf for j in range(-1, WINDOW)):
            continue                                   # the unit heated without the thermostat asking
        if per_day.get(t // 86400, 0.0) < HEATING_DAY_KWH:
            continue
        if sum(r.T_out for r in hrs) / WINDOW >= T_OUT_MAX:
            continue
        items = []
        for r in hrs:
            He = max(0.02, house.H + house.Hw * (r.wind - WIND_REF))
            loss = He * (r.T - r.T_out) - house.g * r.rad - house.internal_at(r.hour)
            reading = r.T_th if r.T_th is not None else r.T + hp.th_diff
            items.append((loss, r.sp - reading, min(1.0, r.dhw_s / 3600), hp.pmax(r.T_out), r.Q))
        out.append((before.Q, items, t))
    return out[-MAX_WINDOWS:]


TRIM = 0.1    # share of the worst windows left out of the error


def window_error(wins, a: float, k: float, offset: float, follow: float, stops: bool = True) -> float | None:
    """Root mean square error of the mean heat per window (kWh per hour). stops: no demand at all stops the unit
    at once, as in the planner's simulator."""
    if not wins:
        return None
    aq = 1 - (1 - min(1.0, max(0.01, follow))) ** 0.25        # per quarter of an hour, as in the planner's simulator
    errs = []
    for w, items, _t in wins:
        tot = meas = 0.0
        for loss, err, dhw, pmax, q in items:
            d = a * loss + k * (err + offset)
            stop = stops and d <= 0
            d = (0.0 if d < 0 else (pmax if d > pmax else d)) * (1.0 - dhw)
            for _ in range(4):
                w = 0.0 if stop else w + aq * (d - w)
                tot += w * 0.25
            meas += q
        errs.append(((tot - meas) / WINDOW) ** 2)
    errs.sort()                                   # the worst windows (cooking, a door open, the unit doing
    keep = errs[:max(1, round(len(errs) * (1 - TRIM)))]   # something else) do not steer the fit
    return (sum(keep) / len(keep)) ** 0.5


def fit(wins, start: dict) -> dict:
    """Search over the grid: two rounds one parameter at a time, then steps to the best neighbour in all four at once
    (the loss share and the offset trade off against each other; one at a time gets stuck)."""
    names = ("follow", "a", "k", "offset")
    cache: dict[tuple, float] = {}

    def err(ix: tuple) -> float:
        if ix not in cache:
            cache[ix] = window_error(wins, **{n: GRID[n][i] for n, i in zip(names, ix)})
        return cache[ix]

    ix = [min(range(len(GRID[n])), key=lambda i: abs(GRID[n][i] - start[n])) for n in names]
    for _ in range(2):
        for d, n in enumerate(names):
            ix[d] = min(range(len(GRID[n])), key=lambda i: err(tuple(ix[:d] + [i] + ix[d + 1:])))
    cur = tuple(ix)
    steps = [(da, db, dc, dd) for da in (-1, 0, 1) for db in (-1, 0, 1) for dc in (-1, 0, 1) for dd in (-1, 0, 1) if (da, db, dc, dd) != (0, 0, 0, 0)]
    for _ in range(60):
        nbrs = [tuple(c + s for c, s in zip(cur, st)) for st in steps]
        nbrs = [x for x in nbrs if all(0 <= x[d] < len(GRID[n]) for d, n in enumerate(names))]
        best = min(nbrs, key=err)
        if err(best) >= err(cur):
            break
        cur = best
    return {n: GRID[n][i] for n, i in zip(names, cur)}


def _params(hp: HeatPumpModel, C: float) -> dict:
    return {"a": hp.a, "k": hp.k if hp.k is not None else C, "offset": hp.offset, "follow": hp.follow}


def learn(rows: list[HourRow], house: HouseModel, previous: HeatPumpModel) -> tuple[HeatPumpModel, str]:
    m = HeatPumpModel.from_dict(previous.as_dict())
    if house.data_from:
        # the house changed (model.learn chose its newest heating days): the response of the old house would mislead
        rows = [r for r in rows if r.ts >= house.data_from]
    notes = []
    d = th_diff(rows)
    if d is not None:
        m.th_diff = d
        notes.append(f"thermostat reads {d:+.1f} °C against the room sensor")

    # lowest steady output and the COP while cycling: only hours with the seconds per state count
    full = sorted(r.Q for r in rows if r.heating_s >= 3300 and r.dhw_s < 60 and r.Q > 0.2)
    if len(full) >= 20:
        m.q_min = round(min(4.0, max(0.3, full[len(full) // 10])), 2)
        notes.append(f"lowest output {m.q_min:.1f} kW")
    part = sorted((r.Q / r.E) / m.cop(r.T_out, r.Q * 3600 / r.heating_s) for r in rows
                  if 300 <= r.heating_s <= 2700 and r.dhw_s < 60 and r.E >= 0.1 and 1.0 <= r.Q / r.E <= 8.0)
    if len(part) >= 20:
        m.cyc = round(min(1.0, max(0.6, part[len(part) // 2])), 2)
        notes.append(f"COP while cycling ×{m.cyc:.2f} ({len(part)} hours)")

    wins = windows(rows, house, m)
    if len(wins) < MIN_WINDOWS:
        notes.append(f"response: {len(wins)} usable windows, need {MIN_WINDOWS}")
        return m, "; ".join(notes)
    cut = int(len(wins) * 0.8)
    train, test = wins[:cut], wins[cut:]
    prev = _params(m, house.C)
    new = fit(train, prev if m.resp_source == "learned" else {"a": 1.0, "k": 1.0, "offset": 0.0, "follow": 0.5})
    default = {"a": 1.0, "k": house.C, "offset": 0.0, "follow": 1.0}
    scores = {"new": window_error(test, **new), "previous": window_error(test, **prev), "default": window_error(test, **default)}
    best = min(scores.values())
    choice = next(n for n in ("previous", "new", "default") if scores[n] <= best * (1 + MARGIN))
    if choice == "new" and scores["new"] < scores["previous"]:
        m.a, m.k, m.offset, m.follow, m.resp_source = new["a"], new["k"], new["offset"], new["follow"], "learned"
        notes.append(f"response learned: {m.a:g} × loss + {m.k:g} kW/°C towards setpoint {m.offset:+.1f} °C, "
                     f"{round(m.follow * 100)} % of a change per hour")
    elif choice == "default" and scores["default"] < scores["previous"]:
        m.a, m.k, m.offset, m.follow, m.resp_source = 1.0, None, 0.0, 1.0, "default"
        notes.append("response: the default predicts better")
    else:
        notes.append("response kept")
    # the last days on their own, fitted without the newest RECENT_MIN windows and judged on those: only a unit that
    # answers differently now (not a week that happened to suit other values) gets through
    held, rest = wins[-RECENT_MIN:], wins[:-RECENT_MIN]
    recent = [w for w in rest if w[2] > rest[-1][2] - RECENT_DAYS * 86400] if rest else []
    if len(recent) >= RECENT_MIN:
        cur = _params(m, house.C)
        rec = fit(recent, cur)
        if window_error(held, **rec) < window_error(held, **cur) * (1 - RECENT_MARGIN):
            m.a, m.k, m.offset, m.follow, m.resp_source = rec["a"], rec["k"], rec["offset"], rec["follow"], "learned"
            notes[-1] = (f"response learned from the last {RECENT_DAYS} days: {m.a:g} × loss + {m.k:g} kW/°C towards "
                         f"setpoint {m.offset:+.1f} °C, {round(m.follow * 100)} % of a change per hour")
    m.resp_hours = len(wins)
    m.resp_error = round(window_error(wins, **_params(m, house.C)), 3)
    return m, "; ".join(notes)


def dhw_profile(samples: list[tuple[int, int, float]]) -> list[float] | None:
    """samples: (local weekday, local hour, share of the hour on hot water) of the last weeks.
    -> 168 shares, Monday 00:00 first. A slot with few samples takes the mean of that hour over all days."""
    if len(samples) < 7 * 24:
        return None
    slot: dict[int, list[float]] = {}
    hour: dict[int, list[float]] = {}
    for wd, h, share in samples:
        s = min(1.0, max(0.0, share))
        slot.setdefault(wd * 24 + h, []).append(s)
        hour.setdefault(h, []).append(s)
    out = []
    for i in range(168):
        xs = slot.get(i) or []
        if len(xs) < 3:
            xs = hour.get(i % 24) or [0.0]
        out.append(round(sum(xs) / len(xs), 3))
    return out
