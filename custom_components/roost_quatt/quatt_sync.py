"""The Quatt heat pump's entities and history: which entities to read, the import from Home Assistant's long-term
statistics (quatt.hours_from_stats), the nightly refresh, the seconds per state Roost counts itself. A mixin of
RoostManager (manager.py): the methods use its state."""
from __future__ import annotations

from .mgr_common import *  # noqa: F401,F403 - the shared imports and constants
from .mgr_common import _LOGGER, _f  # noqa: F401
from homeassistant.components.recorder import statistics
from homeassistant.helpers import device_registry as dr
from . import curve, quatt

STAT_UNITS = {"power": "kW", "temperature": "°C"}      # statistics converted to these, whatever the sensors use
IMPORT_CHUNK_DAYS = 31


class QuattMixin:
    # ------------------------------------------------------------ entities
    def _resolve_quatt(self) -> None:
        """The Quatt integration's entities by role (quatt.QUATT), from the config entry of the chosen CIC device."""
        dev_id = self.conf.get(CONF_HEAT_PUMP)
        dev = dr.async_get(self.hass).async_get(dev_id) if dev_id else None
        if dev is None:
            self.ent, self.pump_name = {}, None
            return
        reg = er.async_get(self.hass)
        found: list[tuple[str | None, str]] = []
        for entry_id in quatt.device_entry_ids(dev):
            found += [(e.unique_id, e.entity_id) for e in er.async_entries_for_config_entry(reg, entry_id)
                      if e.platform == "quatt" and not e.disabled_by]
        self.ent = quatt.resolve(found)
        n = quatt.units(self.ent, self._num(self.ent.get("units")))
        self.pump_name = "Quatt Duo" if n >= 2 else (dev.model if dev.model and dev.model != "—" else "Quatt")

    def pump_state(self) -> str | None:
        st = self._state(self.ent.get("state"))
        return quatt.pump_state(st.state if st else None, self._kw(self.ent.get("power_in")))

    def _track_live(self, t: float) -> None:
        """Count the seconds the unit heats in this hour (more exact than the estimate from the statistics)."""
        dt = min(600.0, max(0.0, t - self._last_tick)) if self._last_tick is not None else 0.0
        state = self.pump_state()
        if state == "boiler" and (self._kw(self.ent.get("boiler_power")) or 0.0) <= quatt.BOILER_KW:
            state = "standby"           # the CIC asks for a boiler that gives no heat (none there, or removed): not a hybrid
        closed = self._live.feed(t, dt, state)
        if closed:
            ts, fields = closed
            self._pump_hours.setdefault(ts, {}).update(fields)

    # ------------------------------------------------------------ the unit
    async def _async_pump_info(self) -> None:
        """What Roost knows of the unit from the Quatt entities: the number of outdoor units, a gas boiler."""
        was = self.hybrid
        n = quatt.units(self.ent, self._num(self.ent.get("units")))
        self.quatt_info = {**self.quatt_info, "units": n, "boiler_entity": bool(self.ent.get("boiler_power")),
                           "at": dt_util.now().isoformat(timespec="seconds")}
        if self.hybrid != was:
            self.event("hybrid", hybrid=self.hybrid, hours=self.boiler_hours)

    def _merge_pump(self, rows: dict[int, dict]) -> None:
        quatt.merge_hours(self._pump_hours, rows)

    # ------------------------------------------------------------ history from the statistics
    async def _async_stats_hours(self, start: datetime, end: datetime) -> dict[int, dict]:
        """The unit's hours in [start, end) from Home Assistant's long-term statistics of the Quatt entities."""
        ids = {role: self.ent[role] for role in quatt.STAT_ROLES if self.ent.get(role)}
        if not ids:
            return {}
        types = {t for role in ids for t in quatt.STAT_ROLES[role]}
        raw = await get_instance(self.hass).async_add_executor_job(
            statistics.statistics_during_period, self.hass, start, end, set(ids.values()), "hour", STAT_UNITS, types)
        by_role: dict[str, dict[int, dict]] = {}
        for role, eid in ids.items():
            rows = {}
            for r in raw.get(eid, []):
                s = r["start"]
                ts = int(s.timestamp() if isinstance(s, datetime) else float(s))
                rows[ts] = {k: _f(r.get(k)) for k in ("mean", "min", "max")}
            by_role[role] = rows
        # the units' standby: measured where enough idle hours are in the window, else as measured before
        sb = quatt.standby_kw(by_role.get("power_in") or {})
        if sb is not None:
            self.quatt_info["standby_kw"] = sb
        return quatt.hours_from_stats(by_role, {"power_in": 1.0, "power_out": 1.0, "boiler_power": 1.0},
                                      standby=sb if sb is not None else self.quatt_info.get("standby_kw", 0.0))

    def import_progress(self) -> tuple[int, int, datetime | None]:
        """A running import: months in, months in all, expected end (local time)."""
        i = self.import_info
        if not self.importing:
            return i.get("months_done", i.get("months", 0)), i.get("months", 0), None
        end = check.import_done_at(i, dt_util.now().timestamp())
        return i.get("months_done", 0), i.get("months", 0), dt_util.as_local(datetime.fromtimestamp(end, tz=timezone.utc))

    async def async_import(self, days: int = IMPORT_DAYS) -> None:
        """Read the heat pump's history from Home Assistant's long-term statistics (newest month first), then learn."""
        if self.importing:
            return
        if not quatt.is_quatt(self.ent):
            self._resolve_quatt()
        if not quatt.is_quatt(self.ent):
            self.import_info = {"status": "no Quatt heat pump found"}
            self._notify()
            return
        self.importing = True
        end = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(days=days)
        months = max(1, -(-days // IMPORT_CHUNK_DAYS))
        self.import_info = {"status": "importing", "from": start.isoformat(), "to": end.isoformat(), "months_done": 0,
                            "months": months, "hours": 0, "at": dt_util.now().isoformat(timespec="seconds")}
        self._notify()
        try:
            hi = end
            while hi > start:
                lo = max(start, hi - timedelta(days=IMPORT_CHUNK_DAYS))
                rows = await self._async_stats_hours(lo, hi)
                self._merge_pump(rows)
                info = self.import_info
                info.update(months_done=info["months_done"] + 1, hours=info["hours"] + len(rows),
                            at=dt_util.now().isoformat(timespec="seconds"))
                self._notify()
                hi = lo
            await self._async_save_history()
            first = min(self._pump_hours) if self._pump_hours else None
            info = self.import_info
            self.event("import", hours=info["hours"], months=info["months_done"])
            self.import_info = {"status": "done", "done": True, "version": quatt.IMPORT_VERSION, "hours": info["hours"], "months": info["months_done"],
                                "from": first and datetime.fromtimestamp(first, tz=timezone.utc).isoformat(),
                                "to": info["to"], "at": dt_util.now().isoformat(timespec="seconds")}
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Roost: import from the statistics failed")
            self.import_info.update(status=f"failed: {err}")
            self.event("error", where="import", error=repr(err)[:200], trace=traceback.format_exc(limit=4)[-800:])
        finally:
            self.importing = False
        await self.async_save()
        if self.import_info.get("done"):
            await self.async_learn()
        self._notify()

    async def _async_refresh_pump(self) -> None:
        """The hours since the last import, from the statistics (nightly, before learning)."""
        await self._async_pump_info()
        if not self.import_info.get("done") or self.importing or not quatt.is_quatt(self.ent):
            return
        end = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
        last = max(self._pump_hours) if self._pump_hours else end.timestamp() - 30 * 86400
        start = max(end - timedelta(days=30), datetime.fromtimestamp(last - 3 * 3600, tz=timezone.utc))
        try:
            rows = await self._async_stats_hours(start, end)
        except Exception as err:  # noqa: BLE001 - learn with what there is
            _LOGGER.debug("Roost: refresh from the statistics skipped: %s", err)
            return
        self._merge_pump(rows)
        self.event("refresh", hours=len(rows))
        await self._async_save_history()

    async def _async_curve(self, rows: list) -> None:
        """The heating curve advice from the house's heat loss, the emitters and the flow temperatures the unit made
        (nightly, after learning). Kept as it was when there is too little data."""
        flows = curve.flows_from_hours(self._pump_hours)
        adv = await self.hass.async_add_executor_job(curve.advise, rows, flows, self.conf.get(CONF_EMITTER, "floor"),
                                                     self.settings().comfort, self.pump.q_min or 0.0, curve.CURVE_X,
                                                     curve.opentherm_from_hours(self._pump_hours))
        if adv is not None:
            self.curve_advice = adv
