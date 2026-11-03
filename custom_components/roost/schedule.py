"""Weekly comfort periods, in local wall time. Pure Python; no thermostat writes.

Periods belong to their start day; an end before its start continues the next day.
Quarter-hour boundaries match the simulator. The legacy daily interval is the default.
"""
from __future__ import annotations

import re
from datetime import datetime

DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
ENABLED = "weekly_comfort"
WEEK = "comfort_schedule"
SECTION = "weekly_schedule"
_PATTERN = re.compile(r"(\d{1,2}):([0-5]\d)\s*[-\u2013]\s*(\d{1,2}):([0-5]\d)")


def parse_day(text: str) -> list[list[int]]:
    if not isinstance(text, str):
        raise ValueError("Periods must be text")
    if not text.strip():
        return []
    out = []
    for item in text.split(","):
        match = _PATTERN.fullmatch(item.strip())
        if not match:
            raise ValueError("Use HH:MM-HH:MM periods separated by commas")
        a, b, c, d = map(int, match.groups())
        start, end = 60*a+b, 60*c+d
        if a >= 24 or c > 24 or (c == 24 and d) or start == end or start % 15 or end % 15:
            raise ValueError("Use nonempty periods on quarter-hour boundaries; 24:00 is an end only")
        out.append([start, end])
    return sorted(out)


def normalise(week: dict) -> dict[str, list[list[int]]]:
    if not isinstance(week, dict) or set(week) - set(DAYS):
        raise ValueError("Unknown weekday")
    out, intervals = {}, []
    for i, day in enumerate(DAYS):
        value = week.get(day, "")
        if isinstance(value, str):
            periods = parse_day(value)
        elif isinstance(value, list):
            periods = []
            for pair in value:
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    raise ValueError("Invalid period")
                start, end = pair
                if (type(start) is not int or type(end) is not int or
                        not 0 <= start < 1440 or not 0 <= end <= 1440 or
                        start == end or start % 15 or end % 15):
                    raise ValueError("Invalid period boundary")
                periods.append([start, end])
            periods.sort()
        else:
            raise ValueError("Invalid weekday")
        out[day] = periods
        for start, end in periods:
            a = i*1440+start
            b = i*1440+(end if end > start else end+1440)
            if b > 10080:
                intervals.extend(((a, 10080), (0, b-10080)))
            else:
                intervals.append((a, b))
    intervals.sort()
    if any(a[1] > b[0] for a, b in zip(intervals, intervals[1:])):
        raise ValueError("Periods overlap, including overnight continuations")
    return out


def format_day(periods: list[list[int]]) -> str:
    def clock(n):
        return f"{n//60:02d}:{n%60:02d}"
    return ", ".join(f"{clock(a)}-{clock(b)}" for a, b in periods)


def context(conf: dict) -> dict:
    if conf.get(ENABLED):
        return {"enabled": True, "week": conf.get(WEEK, {})}
    return {"enabled": False, "day_from": int(conf.get("day_from", 7)),
            "day_to": int(conf.get("day_to", 22))}


def is_comfort(conf: dict, local: datetime) -> bool:
    legacy = int(conf.get("day_from", 7)) <= local.hour < int(conf.get("day_to", 22))
    if not conf.get(ENABLED):
        return legacy
    week = conf.get(WEEK)
    if not isinstance(week, dict) or set(week) != set(DAYS):
        return legacy                  # never silently erase comfort for corrupt legacy configuration
    minute, day = local.hour*60+local.minute, local.weekday()
    try:
        for start, end in week[DAYS[day]]:
            if (end > start and start <= minute < end) or (end < start and minute >= start):
                return True
        return any(end < start and minute < end for start, end in week[DAYS[(day-1)%7]])
    except (TypeError, ValueError):
        return legacy
