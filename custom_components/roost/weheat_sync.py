"""A Weheat heat pump: the Weheat integration's entities, Roost's Weheat login and the heat pump's history (the import in
months, the nightly refresh). A mixin of RoostManager (manager.py, WeheatManager): the methods use its state."""
from __future__ import annotations

from .mgr_common import *  # noqa: F401,F403 - the shared imports and constants
from .mgr_common import _LOGGER, _f, _i, _iso_ts  # noqa: F401
from . import curve
from .weheat_api import async_pump_info, async_settings


class WeheatMixin:
    # ------------------------------------------------------------ entities, the store
    def _resolve_pump(self) -> None:
        """The Weheat integration's entities of the chosen heat pump by role (const.WEHEAT), by their translation_key."""
        reg = er.async_get(self.hass)
        dev_id = self.conf.get(CONF_HEAT_PUMP)
        from homeassistant.helpers import device_registry as dr
        dev = dr.async_get(self.hass).async_get(dev_id) if dev_id else None
        self.pump_name = dev.model or dev.name if dev else None
        by_key = {e.translation_key: e.entity_id for e in er.async_entries_for_device(reg, dev_id, include_disabled_entities=False)} if dev_id else {}
        self.ent = {role: by_key[key] for role, key in WEHEAT.items() if key in by_key}

    def _brand_load(self, data: dict) -> None:
        self.weheat_last = data.get("weheat_last") or self._weheat_last_from_events()
        self.weheat_settings = data.get("weheat_settings") or {}
        self.weheat_pump = data.get("weheat_pump") or {}

    def _brand_save(self) -> dict:
        return {"weheat_settings": self.weheat_settings, "weheat_pump": self.weheat_pump, "weheat_last": self.weheat_last}

    def _elec_since_last(self, t: float) -> float | None:
        """Heating electricity (kWh) since the last tick, from the unit's own meters."""
        # every meter the unit has must read: one missing would make the sum drop, and its return look like new use
        parts = [self._num(self.ent.get(k)) for k in ("elec", "elec_defrost") if self.ent.get(k)]
        if not parts or any(v is None for v in parts):
            return None
        e = sum(parts)
        d = e - self._last_elec if e and self._last_elec is not None and 0 <= e - self._last_elec < 5 else None
        if e:
            self._last_elec = e
        return d

    def boiler_type(self) -> int | None:
        return self.weheat_pump.get("boiler_type")

    def curve_settings(self) -> dict:
        """How the unit is controlled and the heating curve it has (Weheat), for the heating curve sensor."""
        w = self.weheat_settings or {}
        return {"control": w.get("control"), "current": w.get("curve"), "settings_at": w.get("at")}

    # ------------------------------------------------------------ the first run
    async def _async_before_first_run(self) -> None:
        if not self.entry.data.get("token"):
            self._ask_login("not logged in to Weheat yet")     # installed before 0.5.3, or setup without a login

    async def _async_first_pump_info(self) -> None:
        if not self.weheat_pump:
            await self._async_pump_info()

    def _start_import(self) -> bool:
        """The import to start (or carry on with) after the first run. False: none."""
        if not self.import_info.get("done") and self.import_info.get("oldest"):
            # an import in months was cut off by a restart: carry on with the older months
            self.spawn(self.async_import(IMPORT_DAYS), "weheat import (resumed)")
        elif self.import_info.get("done") and self.import_info.get("fields", 1) < WEHEAT_FIELDS:
            # imported by an older version: read the hourly logs again for the newer fields (setpoint, flow
            # temperature); the energy per hour is there already
            self.spawn(self.async_import(IMPORT_DAYS, logs_only=True), "weheat import (new fields)")
        elif self.conf.get(CONF_IMPORT_ON_SETUP) and not self.import_info.get("done"):
            self.spawn(self.async_import(IMPORT_DAYS), "weheat import")
        else:
            return False
        return True

    # ------------------------------------------------------------ the Weheat login and history
    def _weheat_last_from_events(self) -> dict[str, float]:
        """The last Weheat call per kind, from the event log (stored by versions before weheat_last was kept)."""
        last: dict[str, float] = {}
        for e in self.events:
            if e.get("kind") == "weheat_call" and e.get("endpoint") in ("logs", "energy"):
                try:
                    last[e["endpoint"]] = datetime.fromisoformat(e["t"]).timestamp()
                except (KeyError, TypeError, ValueError):
                    pass
        return last

    def _weheat_login(self) -> tuple[str | None, str | None]:
        """(Weheat heat pump id, config entry whose login reads the API: Roost's own)."""
        pump, _ = heat_pump_id(self.hass, self.conf.get(CONF_HEAT_PUMP))
        return pump, self.entry.entry_id

    def _ask_login(self, why: str) -> None:
        """No Weheat login, or Weheat refused it: Home Assistant shows 'Reconfigure / re-authenticate' for Roost."""
        self.event("login_needed", why=why[:200])
        self._notify_user("login")
        self.entry.async_start_reauth(self.hass)

    def _merge_weheat(self, rows: dict[int, dict]) -> None:
        history.merge_hours(self._pump_hours, rows)

    def _energy_before(self, ts: float) -> bool:
        """Most hours of the month before ts have their energy already (an import adding fields, not a first one)."""
        month = [v for t, v in self._pump_hours.items() if ts - 31 * 86400 <= t < ts]
        return len(month) > 24 * 7 and sum(1 for v in month if "q" in v) > 0.8 * len(month)

    def import_progress(self) -> tuple[int, int, datetime | None]:
        """A running Weheat import: months in, months in all, expected end (local time)."""
        i = self.import_info
        if not self.importing:
            return i.get("months_done", i.get("months", 0)), i.get("months", 0), None
        end = check.import_done_at(i, dt_util.now().timestamp(), logs_only=bool(i.get("logs_only")))
        return i.get("months_done", 0), i.get("months", 0), dt_util.as_local(datetime.fromtimestamp(end, tz=timezone.utc))

    async def _async_refresh_pump(self) -> None:
        """The hours since the last import, from Weheat (read-only), so learning and the self-check use the unit's own
        meters and states. Skipped quietly when the Weheat login is not available."""
        pump, weheat_entry = self._weheat_login()
        if not pump or not weheat_entry:
            return
        got = await async_settings(self.hass, weheat_entry, pump)          # how it is controlled, its heating curve
        if got is not None:
            self.weheat_settings = {**got, "at": dt_util.now().isoformat(timespec="seconds")}
        await self._async_pump_info()
        if not self.import_info.get("done") or not self._pump_hours or self.importing:
            return
        end = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
        start = max(end - timedelta(days=30), datetime.fromtimestamp(max(self._pump_hours) - 3 * 3600, tz=timezone.utc))
        try:
            logs, energy, calls = await async_fetch_history(self.hass, weheat_entry, pump, start, end,
                                                            note=lambda **k: self.event("weheat_call", **k),
                                                            last_calls=self.weheat_last)
            self.event("weheat_refresh", calls=calls, hours=len(logs))
        except WeheatLoginNeeded as err:
            self._ask_login(str(err))
            return
        except Exception as err:  # noqa: BLE001 - learn with what there is
            _LOGGER.debug("Roost: Weheat refresh skipped: %s", err)
            return
        self._merge_weheat(history.weheat_hours(logs, energy))
        await self._async_save_history()

    async def _async_pump_info(self) -> None:
        """The unit's fixed data from Weheat (model, gas boiler, hot water tank); kept as it was when Weheat does not
        answer."""
        pump, weheat_entry = self._weheat_login()
        if not pump or not weheat_entry:
            return
        got = await async_pump_info(self.hass, weheat_entry, pump)
        if got is not None:
            was = self.hybrid
            self.weheat_pump = {**got, "at": dt_util.now().isoformat(timespec="seconds")}
            if self.hybrid != was:
                self.event("hybrid", hybrid=self.hybrid, boiler_type=got.get("boiler_type"), hours=self.boiler_hours)

    async def async_import(self, days: int = IMPORT_DAYS, logs_only: bool = False) -> None:
        """Read the heat pump's history from Weheat (read-only), then learn. logs_only: the hours are there already
        (with their energy), only fields of the hourly logs are new: no energy logs, so a year takes half an hour
        instead of hours."""
        if self.importing:
            return
        pump, weheat_entry = self._weheat_login()
        if not pump or not weheat_entry:
            self.import_info = {"status": "no Weheat heat pump found"}
            return
        self.importing = True
        prev = self.import_info if not self.import_info.get("done") and self.import_info.get("oldest") else None
        if prev and prev.get("fields_reading") != WEHEAT_FIELDS:
            # cut off by an update that reads more fields: the months done lack them, so start again from the newest;
            # the hourly logs only when the hours have their energy already
            logs_only = logs_only or self._energy_before(datetime.fromisoformat(prev["oldest"]).timestamp())
            prev = None
        end = datetime.fromisoformat(prev["oldest"]) if prev else dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
        start = datetime.fromisoformat(prev["from"]) if prev else end - timedelta(days=days)
        if prev and not logs_only:
            # carrying on after a restart: logs only when it was, or when the older hours have their energy already
            logs_only = bool(prev.get("logs_only")) or self._energy_before(end.timestamp())
        self.import_info = {"status": "importing", "from": start.isoformat(), "to": (prev or {}).get("to", end.isoformat()),
                            "logs_only": logs_only, "fields_reading": WEHEAT_FIELDS,
                            "oldest": end.isoformat(), "months_done": (prev or {}).get("months_done", 0),
                            "months": max(1, round((end - start).days / 31) + (prev or {}).get("months_done", 0)),
                            "hours": (prev or {}).get("hours", 0)}
        self._notify()
        learned_once = bool(prev)

        async def on_month(logs: list, energy: list, oldest: datetime) -> None:
            nonlocal learned_once
            rows = history.weheat_hours(logs, energy)
            self._merge_weheat(rows)
            await self._async_save_history()
            info = self.import_info
            info.update(oldest=oldest.isoformat(), months_done=info["months_done"] + 1, hours=info["hours"] + len(rows),
                        at=dt_util.now().isoformat(timespec="seconds"))
            await self.async_save()                 # a restart carries on from here
            self._notify()
            if not learned_once:                    # the newest month is in: learn from it now, the rest follows
                learned_once = True
                self.spawn(self.async_learn(), "learning after the first month")
        try:
            calls = await async_fetch_months(self.hass, weheat_entry, pump, start, end, on_month,
                                             lambda **k: self.event("weheat_call", **k), self.weheat_last,
                                             energy_logs=not logs_only)
            info = self.import_info
            first = min(self._pump_hours) if self._pump_hours else None
            self.event("import", hours=info["hours"], calls=calls, months=info["months_done"])
            self.import_info = {"status": "done", "done": True, "fields": WEHEAT_FIELDS, "hours": info["hours"], "calls": calls,
                                "months": info["months_done"],
                                "from": first and datetime.fromtimestamp(first, tz=timezone.utc).isoformat(),
                                "to": info["to"], "at": dt_util.now().isoformat(timespec="seconds")}
        except WeheatUnavailable as err:
            self.import_info.update(status=f"waiting for the Weheat login ({err})")        # keeps how far it got
            self.event("import_waiting", error=str(err)[:200])
            if isinstance(err, WeheatLoginNeeded):
                self._ask_login(str(err))
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Roost: Weheat import failed")
            self.import_info.update(status=f"failed: {err}")
            self.event("error", where="import", error=repr(err)[:200], trace=traceback.format_exc(limit=4)[-800:])
        finally:
            self.importing = False
        await self.async_save()
        if self.import_info.get("done"):
            await self.async_learn()
        self._notify()

    async def _async_curve(self, rows: list) -> None:
        """The heating curve advice from the house's heat loss, the emitters and the unit's flow temperatures (nightly,
        after learning). Kept as it was when there is too little data."""
        if not self.weheat_settings:                    # not asked yet (first night after an update): ask now
            pump, weheat_entry = self._weheat_login()
            got = await async_settings(self.hass, weheat_entry, pump) if pump and weheat_entry else None
            if got is not None:
                self.weheat_settings = {**got, "at": dt_util.now().isoformat(timespec="seconds")}
        flows = curve.flows_from_hours(self._pump_hours)
        adv = await self.hass.async_add_executor_job(curve.advise, rows, flows, self.conf.get(CONF_EMITTER, "floor"),
                                                     self.settings().comfort, self.pump.q_min or 0.0, curve.WEHEAT_X,
                                                     curve.opentherm_from_hours(self._pump_hours))
        if adv is not None:
            self.curve_advice = adv
