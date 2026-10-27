"""Notices (repairs), ready to steer, and watching for a window open. A mixin of RoostManager (manager.py): the methods use its state."""
from __future__ import annotations

from .mgr_common import *  # noqa: F401,F403 - the shared imports and constants
from .mgr_common import _LOGGER, _f, _i, _iso_ts  # noqa: F401
from . import quatt


class HealthMixin:
    def _issue(self, key: str, active: bool, fixable: bool = False, placeholders: dict | None = None,
               translation_key: str | None = None, data: dict | None = None) -> None:
        iid = f"{self.entry.entry_id}_{key}"
        if active != (key in self.health.issues):
            self.event("repair", issue=key, active=active)
        if active and key not in self.health.issues:
            ir.async_create_issue(self.hass, DOMAIN, iid, is_fixable=fixable, severity=ir.IssueSeverity.WARNING,
                                  translation_key=translation_key or key,
                                  data={"entry_id": self.entry.entry_id, "issue": key, **(data or {})} if fixable else None,
                                  translation_placeholders={"name": self.entry.title, **(placeholders or {})})
            self.health.issues.add(key)
        elif not active and key in self.health.issues:
            ir.async_delete_issue(self.hass, DOMAIN, iid)
            self.health.issues.discard(key)

    def _issue_comfort(self) -> None:
        """A comfort setting suggested from the changes made by hand (comfort.suggest); the user accepts or ignores it."""
        c = self.conf

        def local(ts: float) -> tuple[str, int]:
            loc = dt_util.as_local(datetime.fromtimestamp(ts, tz=timezone.utc))
            return loc.date().isoformat(), loc.hour
        def local_minute(ts: float) -> tuple[str, int]:
            loc = dt_util.as_local(datetime.fromtimestamp(ts, tz=timezone.utc))
            return loc.date().isoformat(), loc.hour * 60 + loc.minute
        sched = comfort.scheduled(self.changes, local_minute, time.time())
        self._issue("thermostat_schedule", bool(sched), placeholders={
            "times": ", ".join(f"{s['minute'] // 60:02d}:{s['minute'] % 60:02d} → {s['to']:g} °C" for s in sched)})
        by_schedule = {t for s in sched for t in s["ts"]}
        own = [x for x in self.changes if x["ts"] not in by_schedule]
        if c.get(schedule.ENABLED):
            self.suggestion = None
            self._issue("comfort", False)
            return
        sug = comfort.suggest(own, local, time.time(), int(c[CONF_DAY_FROM]), int(c[CONF_DAY_TO]),
                              float(c[CONF_COMFORT]), float(c[CONF_DAY_MIN]))
        if self.suggestion is not None and (sug is None or sug.as_dict() != self.suggestion.as_dict()):
            self._issue("comfort", False)
        self.suggestion = sug
        if sug is not None:
            cur = {"comfort": c[CONF_COMFORT], "day_from": c[CONF_DAY_FROM], "day_to": c[CONF_DAY_TO]}[sug.key]
            fmt = (lambda v: f"{float(v):g}") if sug.key == "comfort" else (lambda v: f"{int(v)}:00")
            self._issue("comfort", True, fixable=True, translation_key=f"suggest_{sug.kind}", data=sug.as_dict(),
                        placeholders={"current": fmt(cur), "value": fmt(sug.value), "days": str(sug.days), "count": str(sug.count)})

    async def async_accept_suggestion(self, key: str, value: float) -> None:
        """The user accepted a suggested comfort setting: store it (the entry reloads) and start counting afresh."""
        self.changes = []
        self.suggestion = None
        await self.async_save()
        v = int(value) if key in (CONF_DAY_FROM, CONF_DAY_TO) else float(value)
        self.hass.config_entries.async_update_entry(self.entry, options={**self.entry.options, key: v})

    def _issue_ready(self) -> None:
        """Tell the user once the self-check says Roost can steer (only while in shadow mode; the user decides)."""
        rmse = self.check.get("rmse_6h")
        if self.mode == "active" and getattr(self, "_ready_seen", None) is True and not self.ready:
            self._notify_user("steering_not_ready")     # steering on, and the check no longer passes
        self._ready_seen = self.ready
        self._issue("ready_for_active", self.mode == "shadow" and self.ready, fixable=True,
                    placeholders={"rmse": f"{rmse:.2f}" if rmse is not None else "?",
                                  "hours": str(self.check.get("heating_hours", 0)), "days": str(self.check.get("days", 0))})

    def _check_health(self, t: float) -> None:
        # the heat pump heats while the thermostat asks for no heat: it is on its own heating curve
        demand = self._num(self.ent.get("water_setpoint"))
        heating = self.pump_state() == "heating" and (self._kw(self.ent.get("power_in")) or 0.0) > 0.4
        if heating and demand is not None and demand <= 15:
            self.health.not_following_since = self.health.not_following_since or t
        else:
            self.health.not_following_since = None
        self._issue("not_following", bool(self.health.not_following_since and t - self.health.not_following_since > NOT_FOLLOWING_MIN * 60))
        if self.room() is None:
            self.health.room_missing_since = self.health.room_missing_since or t
        else:
            self.health.room_missing_since = None
        self._issue("room_missing", bool(self.health.room_missing_since and t - self.health.room_missing_since > ROOM_SILENT_MIN * 60))
        self._issue("quatt_missing", not quatt.is_quatt(self.ent))
        # Roost steers and the room stays well below its minimum: tell the user (a unit that cannot keep up, a
        # thermostat that does not pass the setpoint on, a model far off)
        room = self.room()
        loc = dt_util.as_local(datetime.fromtimestamp(t, tz=timezone.utc))
        low = (self.settings().away_min if self.is_away(t) else
               float(self.conf[CONF_DAY_MIN]) if self.is_day(loc) else float(self.conf[CONF_NIGHT_MIN]))
        if self.mode == "active" and room is not None and room < low - HOUSE_COLD_K and not self.window.active():
            self.health.house_cold_since = self.health.house_cold_since or t
        else:
            self.health.house_cold_since = None
        cold = bool(self.health.house_cold_since and t - self.health.house_cold_since >= HOUSE_COLD_MIN * 60)
        if cold and "house_cold" not in self.health.issues:
            self._notify_user("house_cold", room=f"{room:.1f}", minimum=f"{low:g}")
        self._issue("house_cold", cold, placeholders={"room": f"{room:.1f}" if room is not None else "?", "minimum": f"{low:g}"})

    @property
    def following(self) -> bool | None:
        if not self.ent.get("water_setpoint"):
            return None
        return not (self.health.not_following_since and time.time() - self.health.not_following_since > NOT_FOLLOWING_MIN * 60)

    def _windows_open(self) -> bool | None:
        """The chosen window/door sensors: True when one is open, None when none are chosen (or none report)."""
        ids = self.conf.get(CONF_WINDOW_SENSORS) or []
        states = [self._state(e) for e in ids]
        known = [s.state for s in states if s is not None and s.state in ("on", "off")]
        return ("on" in known) if known else None

    def _watch_window(self, t: float) -> None:
        ev = self.window.feed(t, self.room(), self._windows_open())
        if ev == "open":
            self.event("window", phase="open", via=self.window.via, before=self.window.before, room=self.room())
            self._notify()
        elif ev == "end":
            self.event("window", phase="end", room=self.room())
            self.window.prune(t - 400 * 86400)
            if self._airing_from is not None:
                self._airing_from = None
                self.mem.last_write = None          # back to the plan at once, not after the change interval
            # the room is not what the plan expected any more: plan afresh
            self.hass.async_create_background_task(self._async_tick(None, force_plan="window"), "roost: plan after airing")
            self._notify()

    def ready_eta(self) -> tuple[str, datetime | None]:
        """What Roost still waits for before it can steer, and when it expects that (local time, or None)."""
        now = dt_util.now()
        nxt = now.replace(hour=LEARN_HOUR, minute=LEARN_MINUTE, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        missing = [] if self.ready else (self.ready_missing or ["temperature"])
        code, ts = check.eta(missing, self.check, self.import_info if self.importing else {}, now.timestamp(), nxt.timestamp())
        return code, dt_util.as_local(datetime.fromtimestamp(ts, tz=timezone.utc)) if ts else None
