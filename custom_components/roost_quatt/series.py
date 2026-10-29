"""Read time series (prices, solar forecasts) from the attributes of common Home Assistant sensors.

Pure Python, no Home Assistant imports, so it can be tested on its own.

Supported shapes (detected automatically):
- a list of dicts with a start, an optional end and a value, under any attribute name. Key names that are
  recognised: start/from/time/startsAt/start_time/period_start/valid_from, end/till/to/end_time/period_end/valid_to,
  value/price/rate/total/pv_estimate/value_inc_vat. Nord Pool (raw_today/raw_tomorrow), ENTSO-e (prices),
  Frank Energie (prices), evcc (rates), Solcast (detailedForecast) and many others use this shape.
- a dict of ISO timestamps to numbers (Predbat style results).
- Nord Pool style plain number lists in `today` and `tomorrow` (equal slots over the local day).
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

START_KEYS = ("start", "from", "time", "startsAt", "starts_at", "start_time", "period_start", "valid_from", "datetime", "date",
              "start_date")
END_KEYS = ("end", "till", "to", "end_time", "period_end", "valid_to", "endsAt", "ends_at", "end_date")
VALUE_KEYS = ("value", "price", "rate", "total", "value_inc_vat", "pv_estimate", "price_ct", "energy", "power",
              "electricity_price", "price_tax_included")   # Zonneplan: per hour, and per quarter as {"amount": …}

Slot = tuple[float, float, float]          # (start epoch s, end epoch s, value)


def to_ts(value: Any) -> float | None:
    """Epoch seconds from a datetime, an ISO string or an epoch number."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    if isinstance(value, (int, float)):
        v = float(value)
        return v / 1000 if v > 1e11 else v
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        # 2026-10-13T21:10:00+0200 -> +02:00
        if len(s) > 5 and (s[-5] in "+-") and s[-4:].isdigit() and ":" not in s[-5:]:
            s = s[:-2] + ":" + s[-2:]
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    return None


def _num(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def _first(d: dict, keys: Iterable[str]) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _close_ends(points: list[tuple[float, float | None, float]]) -> list[Slot]:
    """Fill in missing end times from the next start (last slot: same length as the one before, else 1 h)."""
    points.sort(key=lambda p: p[0])
    out: list[Slot] = []
    for i, (s, e, v) in enumerate(points):
        if e is None:
            if i + 1 < len(points):
                e = points[i + 1][0]
            elif out:
                e = s + (out[-1][1] - out[-1][0])
            else:
                e = s + 3600
        if e > s:
            out.append((s, e, v))
    return out


def slots_from_list(items: list) -> list[Slot]:
    pts: list[tuple[float, float | None, float]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        raw = _first(it, VALUE_KEYS)
        s, v = to_ts(_first(it, START_KEYS)), _num(raw.get("amount") if isinstance(raw, dict) else raw)
        if s is None or v is None:
            continue
        pts.append((s, to_ts(_first(it, END_KEYS)), v))
    return _close_ends(pts)


def slots_from_dict(d: dict) -> list[Slot]:
    pts = []
    for k, v in d.items():
        s, x = to_ts(k), _num(v)
        if s is not None and x is not None:
            pts.append((s, None, x))
    return _close_ends(pts)


def slots_from_day_list(values: list, day_start_ts: float, day_end_ts: float | None = None) -> list[Slot]:
    """A list of prices for one local day, evenly over it. day_end_ts: the next local midnight, so a day of 23 or 25
    hours (daylight saving time) gets its own length (R06); without it a day is 24 hours."""
    vals = [_num(v) for v in values]
    if not vals:
        return []
    step = ((day_end_ts if day_end_ts is not None else day_start_ts + 86400) - day_start_ts) / len(vals)
    return [(day_start_ts + i * step, day_start_ts + (i + 1) * step, v) for i, v in enumerate(vals) if v is not None]


def find_slots(attributes: dict, local_midnight_ts: float | None = None, midnights: list[float] | None = None) -> list[Slot]:
    """All slots found in the attributes of one entity, merged and de-duplicated (later sources win per start)."""
    found: dict[float, Slot] = {}
    for key, val in (attributes or {}).items():
        slots: list[Slot] = []
        if isinstance(val, list) and val and isinstance(val[0], dict):
            slots = slots_from_list(val)
        elif isinstance(val, dict) and len(val) >= 3 and sum(1 for k in list(val)[:5] if to_ts(k)) >= 3:
            slots = slots_from_dict(val)
        elif (key in ("today", "tomorrow") and isinstance(val, list) and val and local_midnight_ts is not None
              and all(isinstance(x, (int, float)) or x is None for x in val)):
            if midnights and len(midnights) >= 3:      # today, tomorrow and the day after, as local midnights
                d = 1 if key == "tomorrow" else 0
                slots = slots_from_day_list(val, midnights[d], midnights[d + 1])
            else:
                slots = slots_from_day_list(val, local_midnight_ts + (86400 if key == "tomorrow" else 0))
        for sl in slots:
            found[sl[0]] = sl
    return sorted(found.values())


def price_scale(unit: str | None, values: list[float]) -> float:
    """Factor to get currency per kWh. Cents and per-MWh units are recognised; otherwise a plausibility guess."""
    u = (unit or "").lower().replace(" ", "")
    if "mwh" in u:
        return 0.001
    if "ct" in u or "cent" in u or u.startswith("c/") or u.startswith("p/") or "pence" in u:
        return 0.01
    if values:
        med = sorted(abs(v) for v in values)[len(values) // 2]
        if med > 5000:                    # raw units, e.g. Zonneplan's 1e-7 euro: down to a price of 0.1–1 per kWh
            return 10.0 ** -math.ceil(math.log10(med))
        if med > 200:                     # per MWh
            return 0.001
        if med > 5:                       # 5 per kWh is not a realistic price; it is cents
            return 0.01
    return 1.0


def slot_scale(slots: list[Slot], unit: str | None, state: float | None, now_ts: float) -> float:
    """Factor for a forecast's values to currency per kWh. When the sensor's own value is known (already in currency
    per kWh), the power of ten that makes the forecast's value for now match it: some integrations keep the forecast in
    other units than their state (Zonneplan: 1e-7 euro). Else from the unit, or a plausibility guess."""
    now_v = current_value(slots, now_ts) if state is not None and abs(state) >= 0.01 else None
    if now_v:
        r = state / now_v
        if r > 0:
            p = round(math.log10(r))
            if abs(math.log10(r) - p) < 0.35:           # the same price within about a factor 2
                return 10.0 ** p
    return price_scale(unit, [v for *_, v in slots])


def hourly(slots: list[Slot], start_ts: float, hours: int, fill_last: bool = True, full: bool = False) -> list[float | None]:
    """Time-weighted average per hour from start_ts (hour 0 may be a partial hour: averaged over what is left).
    full: an hour only counts when its slots cover all of it (what is left of hour 0); a price for its first quarter
    is not a price for the hour (R05)."""
    out: list[float | None] = []
    last: float | None = None
    for h in range(hours):
        a = start_ts if h == 0 else _hour_floor(start_ts) + h * 3600
        b = _hour_floor(start_ts) + (h + 1) * 3600
        tot = w = 0.0
        for s, e, v in slots:
            ov = min(b, e) - max(a, s)
            if ov > 0:
                tot += v * ov
                w += ov
        if w > 0 and not (full and w < (b - a) - 1):
            last = tot / w
            out.append(last)
        else:
            out.append(last if fill_last else None)
    return out


def _hour_floor(ts: float) -> float:
    return ts - (ts % 3600)


def published_prefix(values: list[float | None]) -> list[float]:
    """Only contiguous known prices from now. Never bridge a gap with a historical or last price."""
    out = []
    for v in values:
        if v is None or not math.isfinite(v):
            break
        out.append(v)
    return out


def slots_from_changes(changes: list[tuple[float, float]], end_ts: float) -> list[Slot]:
    """Slots from state changes (epoch s, value), each valid until the next change (the last one until end_ts)."""
    ch = sorted(changes)
    return [(t, ch[i + 1][0] if i + 1 < len(ch) else end_ts, v) for i, (t, v) in enumerate(ch) if (ch[i + 1][0] if i + 1 < len(ch) else end_ts) > t]


def fill_gaps(vals: list[float | None], start_ts: float, seen: dict[int, float],
              fallback: float | None = None) -> tuple[list[float | None], list[bool]]:
    """Fill hours the forecast does not reach yet (day-ahead prices for tomorrow often arrive in the afternoon):
    the same clock hour one day earlier, else two days earlier, else the last known value. Returns (values, guessed)."""
    out, guessed, last = [], [], fallback
    base = int(_hour_floor(start_ts))
    for h, v in enumerate(vals):
        if v is not None:
            last = v
            out.append(v)
            guessed.append(False)
            continue
        ts = base + h * 3600
        prev = seen.get(ts - 86400, seen.get(ts - 2 * 86400))
        out.append(prev if prev is not None else last)
        guessed.append(True)
    return out, guessed


def energy_per_hour(slots: list[Slot], start_ts: float, hours: int, rate_first: bool = False) -> list[float]:
    """kWh per hour from slots holding average power in kW (Solcast style): integral of power over the hour.
    rate_first: hour 0 as a rate over a whole hour (the mean power of what is left of it, at least the last quarter),
    as the planner and the house use count with whole hours (R09)."""
    out = []
    for h in range(hours):
        a = start_ts if h == 0 else _hour_floor(start_ts) + h * 3600
        b = _hour_floor(start_ts) + (h + 1) * 3600
        e = 0.0
        for s, en, v in slots:
            ov = min(b, en) - max(a, s)
            if ov > 0:
                e += v * ov / 3600
        if h == 0 and rate_first:
            e *= 3600 / max(900.0, b - a)
        out.append(max(0.0, e))
    return out


def current_value(slots: list[Slot], now_ts: float) -> float | None:
    for s, e, v in slots:
        if s <= now_ts < e:
            return v
    return None


def horizon_hours(slots: list[Slot], now_ts: float) -> float:
    """How far ahead the series reaches (hours)."""
    if not slots:
        return 0.0
    return max(0.0, (max(e for _, e, _ in slots) - now_ts) / 3600)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def local_midnight(now: datetime) -> float:
    """Midnight of the local day of `now` (aware datetime), as epoch seconds."""
    loc = now.astimezone()
    return (loc - timedelta(hours=loc.hour, minutes=loc.minute, seconds=loc.second, microseconds=loc.microsecond)).timestamp()


FLAT_EPS = 0.002        # currency per kWh: prices this close are the same price
TOU_LEVELS = 3          # a contract with at most this many rates by the hour of day (normal / low)
FIT_MIN_HOURS = 12      # hours of a sensor's history beside day-ahead prices before Roost estimates from them
FIT_MIN_R2 = 0.7        # how closely the sensor must follow the day-ahead price (share of its variation explained)


def classify_history(hist: dict[int, float], local_hour) -> str:
    """What a price sensor without a forecast is, from its hourly history: "flat" (one price), "tou" (a fixed rate per
    hour of the day: normal/low), "dynamic" (changes from hour to hour, a day-ahead contract) or "unknown" (too little
    history)."""
    vals = [v for _, v in sorted(hist.items())[-48:]]
    if len(vals) < FIT_MIN_HOURS:
        return "unknown"
    if max(vals) - min(vals) < FLAT_EPS:
        return "flat"
    by_hour: dict[int, list[float]] = {}
    for ts, v in sorted(hist.items())[-48:]:
        by_hour.setdefault(local_hour(ts), []).append(v)
    levels = sorted({round(v / FLAT_EPS) for v in vals})
    if all(max(x) - min(x) < FLAT_EPS for x in by_hour.values()) and len(levels) <= TOU_LEVELS:
        return "tou"
    return "dynamic"


def fit_line(pairs: list[tuple[float, float]]) -> tuple[float, float, float] | None:
    """Least squares y = a·x + b over (x, y) pairs -> (a, b, r²), None with too few pairs or no variation."""
    n = len(pairs)
    if n < FIT_MIN_HOURS:
        return None
    mx = sum(x for x, _ in pairs) / n
    my = sum(y for _, y in pairs) / n
    sxx = sum((x - mx) ** 2 for x, _ in pairs)
    syy = sum((y - my) ** 2 for _, y in pairs)
    if sxx <= 1e-12 or syy <= 1e-12:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in pairs)
    a = sxy / sxx
    b = my - a * mx
    return a, b, sxy * sxy / (sxx * syy)
