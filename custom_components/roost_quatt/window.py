"""A window open: airing the room. Recognised from the room temperature (a fast drop no house makes by itself, and
at least two steps of the reading: a thermostat that shows half degrees must fall 1 °C) or from window/door sensors
when the user chose them. Pure Python.

While a window is open, and until the room has come back, Roost does not touch the thermostat (it would heat the
outdoors), and the hours involved are left out of everything Roost learns from: the correction from the last hours,
the nightly self-check, the heat pump's response and the house model. Otherwise a few minutes of airing look like a
house that suddenly loses much more heat.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

DROP_K = 0.5            # °C the room falls ...
DROP_MIN = 15           # ... within this many minutes: a window (a floor-heated room cools ~0.1 °C an hour)
DROP_STEPS = 2          # and at least this many of the reading's steps: a thermostat that shows 0.5 °C steps drops
                        # 0.5 °C at once when the room cools a tenth past a rounding point, and flips back and forth
STEPS_KEPT = 20         # the changes of the reading remembered to see its step
SETTLE_MIN = 10         # the room has stopped falling for this long: the window is closed
RECOVER_K = 0.2         # the episode ends when the room is back within this of where it was ...
RECOVER_MAX_MIN = 90    # ... or this long after the window closed
MAX_MIN = 180           # an episode never lasts longer (a sensor that sticks, a door left open)


def reading_step(values) -> float:
    """The smallest change between readings that differ (°C): 0.1 for a room sensor, 0.5 for a thermostat that
    rounds to half degrees. 0 when the readings did not change."""
    out, last = 0.0, None
    for v in values:
        if v is None:
            continue
        if last is not None and abs(v - last) >= 0.01:
            out = abs(v - last) if not out else min(out, abs(v - last))
        last = v
    return round(out, 3)


@dataclass
class WindowWatch:
    samples: deque = field(default_factory=lambda: deque(maxlen=60))   # (t, room)
    open_at: float | None = None
    closed_at: float | None = None
    before: float | None = None         # the room just before it fell
    low: float | None = None            # the lowest room since
    low_at: float | None = None
    via: str = ""                       # "drop" or "contact"
    stuck: bool = False                 # ended by MAX_MIN with the sensor still open: ignore it until it closes once
    hours: set = field(default_factory=set)    # hour starts touched by an episode (not to learn from)
    changes: deque = field(default_factory=lambda: deque(maxlen=STEPS_KEPT))   # the last readings that differed

    def active(self) -> bool:
        return self.open_at is not None

    def feed(self, t: float, room: float | None, contact_open: bool | None = None) -> str | None:
        """A new reading (and the window sensors: True = one is open, None = none chosen). -> "open" when an episode
        starts, "end" when it ends, else None."""
        if room is not None:
            self.samples.append((t, room))
            while self.samples and t - self.samples[0][0] > 40 * 60:
                self.samples.popleft()
            if not self.changes or abs(room - self.changes[-1]) >= 0.01:
                self.changes.append(room)
        if self.open_at is None:
            start = self._starts(t, room, contact_open)
            if start:
                return start
            return None
        self._mark(t)
        if room is not None and (self.low is None or room < self.low - 0.02):
            self.low, self.low_at = room, t
        if self.closed_at is None:
            closed = (not contact_open) if contact_open is not None else \
                (self.low_at is not None and t - self.low_at >= SETTLE_MIN * 60)
            if closed:
                self.closed_at = t
        back = room is not None and self.before is not None and room >= self.before - RECOVER_K
        if (self.closed_at is not None and (back or t - self.closed_at >= RECOVER_MAX_MIN * 60)) or t - self.open_at >= MAX_MIN * 60:
            self.stuck = bool(contact_open) and self.closed_at is None
            self.open_at = self.closed_at = self.before = self.low = self.low_at = None
            return "end"
        return None

    def _starts(self, t: float, room: float | None, contact_open: bool | None) -> str | None:
        recent = [(ts, v) for ts, v in self.samples if t - ts <= DROP_MIN * 60]
        peak = max((v for _, v in recent), default=None)
        if contact_open is False:
            self.stuck = False
        if contact_open and not self.stuck:
            self._open(t, peak if peak is not None else room, "contact")
            return "open"
        drop = max(DROP_K, DROP_STEPS * reading_step(self.changes) - 0.01)
        if room is not None and peak is not None and peak - room >= drop and not (contact_open and self.stuck):
            self._open(t, peak, "drop")
            return "open"
        return None

    def _open(self, t: float, before: float | None, via: str) -> None:
        self.open_at, self.closed_at, self.before, self.via = t, None, before, via
        self.low, self.low_at = None, None
        self._mark(t - DROP_MIN * 60)           # the drop began before it was seen
        self._mark(t)

    def _mark(self, t: float) -> None:
        self.hours.add(int(t // 3600 * 3600))

    def prune(self, before_ts: float) -> None:
        self.hours = {h for h in self.hours if h >= before_ts}
