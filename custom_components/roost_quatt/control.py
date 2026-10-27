"""From the planned setpoint to a thermostat command. Pure Python.

- Only send when the planned setpoint differs from what the thermostat has (or, in shadow mode, would have).
- At most one change per `min_interval_min` (default 60), so the heat pump runs calmly; a room below the hard minimum
  may be corrected at once.
- A setpoint changed by someone else pauses Roost for `pause_hours`; the manager detects that (its own commands carry
  their own context).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .reasons import Reason


@dataclass
class ControlSettings:
    min_interval_min: float = 60.0
    pause_hours: float = 2.0
    tolerance: float = 0.25


@dataclass
class ControlMemory:
    last_write: float | None = None
    last_sp: float | None = None
    pause_until: float | None = None
    virtual_sp: float | None = None         # shadow mode: what the thermostat would have now
    away_until: float | None = None         # nobody home until then: the away minimum, no comfort hours
    away_min: float | None = None

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "ControlMemory":
        m = cls()
        for k, v in (d or {}).items():
            if hasattr(m, k):
                setattr(m, k, v)
        return m


@dataclass
class Decision:
    setpoint: float | None        # send this, or None
    why: Reason
    effective: float | None       # what the thermostat has (or would have) after this decision

    @property
    def reason(self) -> str:
        return str(self.why)

    def as_dict(self) -> dict:
        return {"setpoint": self.setpoint, "why": self.why.as_dict(), "effective": self.effective}


def decide(now: float, planned: float | None, thermostat_sp: float | None, room: float | None, hard_min: float,
           mem: ControlMemory, cs: ControlSettings, active: bool) -> Decision:
    current = thermostat_sp if (active or mem.virtual_sp is None) else mem.virtual_sp
    if planned is None:
        return Decision(None, Reason("no_plan"), current)
    if mem.pause_until and now < mem.pause_until:
        mins = round((mem.pause_until - now) / 60)
        return Decision(None, Reason("paused", {"min": mins}), current)
    if current is not None and abs(planned - current) < cs.tolerance:
        return Decision(None, Reason("already_right"), current)
    urgent = room is not None and room < hard_min - 0.3 and (current is None or planned > current)
    if not urgent and mem.last_write is not None and (now - mem.last_write) / 60 < cs.min_interval_min:
        wait = cs.min_interval_min - (now - mem.last_write) / 60
        return Decision(None, Reason("wait", {"min": round(wait)}), current)
    mem.last_write, mem.last_sp = now, planned
    if not active:
        mem.virtual_sp = planned
    return Decision(planned, Reason("urgent" if urgent else "following"), planned)
