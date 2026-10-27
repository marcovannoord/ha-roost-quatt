"""Learn comfort from the changes people make by hand: a suggestion, never a change by itself. Pure Python.

Roost records every change of the thermostat that it did not make itself while it steers (in shadow mode another
controller may be steering, so those changes say nothing about comfort). When the same kind of change keeps coming
back on different days, it suggests a setting:

- turned up during the comfort hours        -> a higher comfort temperature
- turned down during the comfort hours      -> a lower comfort temperature (not below the day minimum)
- turned up shortly before the comfort hours -> start them earlier
- turned up shortly after the comfort hours  -> end them later
- turned down near the end of the comfort hours -> end them earlier
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

SCHEDULE_MIN = 3        # minutes: changes this close in time of day, to the same temperature, on 3+ days = a schedule

WINDOW_DAYS = 14
MIN_DAYS = 3            # the same kind of change on at least this many different days
MIN_STEP = 0.4          # °C: smaller changes are fiddling
EDGE_HOURS = 3          # "shortly before/after" the comfort hours


@dataclass
class Suggestion:
    kind: str           # raise_comfort | lower_comfort | earlier_day | later_day | earlier_night
    key: str            # the setting to change
    value: float        # its new value
    days: int           # different days with such a change
    count: int          # changes

    def as_dict(self) -> dict:
        return {"kind": self.kind, "key": self.key, "value": self.value, "days": self.days, "count": self.count}


def _median(xs: list[float]) -> float:
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def scheduled(changes: list[dict], local_minute: Callable[[float], tuple[str, int]], now_ts: float) -> list[dict]:
    """Changes that come back at the same time of day (within SCHEDULE_MIN minutes) to the same temperature on at least
    MIN_DAYS different days: a schedule in the thermostat itself, or another automation — not a person. -> one entry
    per schedule: {"minute", "to", "days", "ts": [the changes]}. local_minute(ts) -> (local date, minute of the day)."""
    recent = [c for c in changes if now_ts - c["ts"] <= WINDOW_DAYS * 86400]
    pts = sorted(((local_minute(c["ts"]), c) for c in recent), key=lambda x: (round(x[1]["to"] * 2), x[0][1]))
    out, used = [], set()
    for i, ((_d, m), c) in enumerate(pts):
        if c["ts"] in used:
            continue
        group = [(d2, c2) for (d2, m2), c2 in pts[i:] if abs(c2["to"] - c["to"]) < 0.05 and 0 <= m2 - m <= 2 * SCHEDULE_MIN
                 and c2["ts"] not in used]
        days = {d2 for d2, _c2 in group}
        if len(days) >= MIN_DAYS:
            used |= {c2["ts"] for _d2, c2 in group}
            out.append({"minute": m, "to": c["to"], "days": len(days), "ts": [c2["ts"] for _d2, c2 in group]})
    return out


def _r(x: float) -> float:
    return round(x * 2) / 2


def from_history(samples: list[tuple[int, float]]) -> dict | None:
    """Comfort settings from the thermostat's last weeks: samples (local hour, setpoint) for every hour.
    The comfort hours are the longest run of hours whose usual setpoint is in the upper half; the comfort temperature is
    their usual setpoint; the night minimum the usual night setpoint, but at most 1.5 °C below comfort (a heat pump does
    badly with a deep night setback); the day minimum half a degree below comfort; storing heat up to 2 °C above it."""
    per: dict[int, list[float]] = {}
    for h, sp in samples:
        if 5.0 <= sp <= 30.0:
            per.setdefault(h % 24, []).append(sp)
    if len(per) < 20 or sum(len(v) for v in per.values()) < 24 * 3:          # three days are enough for a start
        return None
    med = {h: _median(v) for h, v in per.items()}
    hi, lo = max(med.values()), min(med.values())
    if hi - lo >= 0.5:
        mid = (hi + lo) / 2
        warm = [h for h in range(24) if med.get(h, lo) >= mid]
        best, cur = [], []
        for h in list(range(24)) * 2:                       # twice round: a run may pass midnight
            cur = cur + [h] if h in warm and len(cur) < 24 else ([h] if h in warm else [])
            if len(cur) > len(best):
                best = list(cur)
        day_from, day_to = best[0], (best[-1] + 1) % 24 or 24
        if day_to <= day_from:                             # a run through midnight: keep a plain day
            day_from, day_to = 7, 22
        comfort = _r(_median([med[h] for h in best if h in med]))
        night = _r(_median([med[h] for h in med if h not in best])) if len(best) < 24 else comfort - 1.0
    else:
        day_from, day_to = 7, 22
        comfort = _r(_median(list(med.values())))
        night = comfort - 1.0
    comfort = max(18.0, min(23.0, comfort))
    night = max(16.0, max(comfort - 1.5, min(comfort, night)))
    return {"day_from": day_from, "day_to": day_to, "comfort": comfort, "day_min": comfort - 0.5,
            "night_min": night, "store_max": min(25.0, comfort + 2.0)}


def suggest(changes: list[dict], local: Callable[[float], tuple[str, int]], now_ts: float, day_from: int, day_to: int,
            comfort: float, day_min: float) -> Suggestion | None:
    """changes: [{"ts", "from", "to"}]; local(ts) -> (local date, local hour). The pattern seen on the most days wins.
    Leave out changes made by a schedule (scheduled()) first."""
    groups: dict[str, list[tuple[str, int, float]]] = {k: [] for k in ("raise_comfort", "lower_comfort", "earlier_day", "later_day", "earlier_night")}
    for c in changes:
        if now_ts - c["ts"] > WINDOW_DAYS * 86400:
            continue
        delta = c["to"] - c["from"]
        if abs(delta) < MIN_STEP:
            continue
        date, h = local(c["ts"])
        day = day_from <= h < day_to
        if delta > 0 and day_from - EDGE_HOURS <= h < day_from:
            groups["earlier_day"].append((date, h, delta))
        elif delta > 0 and day_to <= h < day_to + EDGE_HOURS:
            groups["later_day"].append((date, h, delta))
        elif delta < 0 and day and h >= day_to - 2:
            groups["earlier_night"].append((date, h, delta))
        elif delta > 0 and day:
            groups["raise_comfort"].append((date, h, delta))
        elif delta < 0 and day:
            groups["lower_comfort"].append((date, h, delta))
    best: Suggestion | None = None
    for kind, xs in groups.items():
        days = len({d for d, _h, _x in xs})
        if days < MIN_DAYS:
            continue
        step = round(_median([abs(x) for _d, _h, x in xs]) * 2) / 2 or 0.5
        hour = int(_median([h for _d, h, _x in xs]))
        if kind == "raise_comfort":
            s = Suggestion(kind, "comfort", min(24.0, comfort + step), days, len(xs))
        elif kind == "lower_comfort":
            s = Suggestion(kind, "comfort", max(day_min, comfort - step), days, len(xs))
        elif kind == "earlier_day":
            s = Suggestion(kind, "day_from", min(h for _d, h, _x in xs), days, len(xs))
        elif kind == "later_day":
            s = Suggestion(kind, "day_to", min(24, max(h for _d, h, _x in xs) + 1), days, len(xs))
        else:
            s = Suggestion(kind, "day_to", max(day_from + 1, hour), days, len(xs))
        current = {"comfort": comfort, "day_from": day_from, "day_to": day_to}[s.key]
        if s.value == current:
            continue
        if best is None or s.days > best.days:
            best = s
    return best


def adjust_settings(c: dict, changed: set[str]) -> dict | None:
    """The temperatures and comfort hours after a change from the card: the setting that was changed wins, the others
    follow it (comfort never below the day minimum, storing never below comfort, the lowest setpoint never above
    comfort). c: comfort, day_min, night_min, store_max, lowest_setpoint, day_from, day_to. None when the comfort hours
    would end before they start."""
    if int(c["day_to"]) <= int(c["day_from"]):
        return None
    f = {k: round(float(c[k]) * 2) / 2 for k in ("comfort", "day_min", "night_min", "store_max", "lowest_setpoint")}
    if "day_min" in changed and f["day_min"] > f["comfort"]:
        f["comfort"] = f["day_min"]
    f["day_min"] = min(f["day_min"], f["comfort"])
    if f["store_max"] < f["comfort"]:
        if "store_max" in changed:
            f["comfort"] = f["store_max"]
            f["day_min"] = min(f["day_min"], f["comfort"])
        else:
            f["store_max"] = f["comfort"]
    if f["lowest_setpoint"] > f["comfort"]:
        if "lowest_setpoint" in changed:
            f["comfort"] = f["lowest_setpoint"]
            f["store_max"] = max(f["store_max"], f["comfort"])
        else:
            f["lowest_setpoint"] = f["comfort"]
    return {**f, "day_from": int(c["day_from"]), "day_to": int(c["day_to"])}
