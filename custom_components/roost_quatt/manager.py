"""Runtime of one Roost entry: read sources, keep track of stored heat, plan, steer the thermostat, learn.

Split by subject: prices (prices.py), the Quatt entities and history (quatt_sync.py), the hourly log and the look back
(hourlog.py), notices and watching for a window open (health.py); shared imports and constants in mgr_common.py."""
from __future__ import annotations

from .mgr_common import *  # noqa: F401,F403 - the shared imports and constants
from .mgr_common import _LOGGER, _f, _i, _iso_ts  # noqa: F401
from . import curve, quatt, replan, savings
from .care import CareMixin
from .health import HealthMixin
from .hourlog import HourLogMixin
from .prices import PricesMixin
from .quatt_sync import QuattMixin


class RoostManager(PricesMixin, QuattMixin, HourLogMixin, HealthMixin, CareMixin):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._hist_store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.history")
        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[Callable[[], None]] = []
        self._contexts: dict[str, float] = {}
        self.mode = "shadow"
        self.ent: dict[str, str] = {}               # Quatt role -> entity_id (quatt.QUATT)
        self.pump_name: str | None = None
        self.house = model.HouseModel()
        self.pump = heatpump.HeatPumpModel()
        self.mem = control.ControlMemory()
        self.storage_e = 0.0
        self.plan: planner.Plan | None = None
        self.plan_hours: list[planner.HourIn] = []
        self.plan_at: float | None = None
        self.plan_tariff: list[float] = []          # published import price per plan hour
        self.plan_guess: list[bool] = []            # legacy diagnostic shape; new plans contain only known tariffs
        self.plan_on_guess = False                  # legacy snapshot field; no guessed prices in new plans
        self.boiler_hours = 0                       # hours a gas boiler ran in the last year: a hybrid (history.boiler_hours)
        self.replayed_with: int | None = None       # planner.REPLAY_VERSION the days kept were replayed with
        # price entity -> {hour epoch: price per kWh}: retained history, never a source of unpublished future tariffs
        self.price_seen: dict[str, dict[int, float]] = {}
        self._price_guess: dict[str, list[bool]] = {}
        self.reason = Reason("starting")
        self.decision: control.Decision | None = None
        self.sources: dict[str, str] = {}
        self.learn_info: dict = {}
        self.import_info: dict = {}
        self.hour_log: list[dict] = []              # last ~48 h: state and inputs per hour, for the daily saving
        self.saving_days: dict[str, float] = {}     # date -> saving (currency)
        self.saving_detail: dict[str, dict] = {}    # date -> the saving per hour (planner.breakdown), the last days
        self.day_contexts: dict[str, dict] = {}      # immutable model/settings used to validate each local day
        self.plan_changes: list[dict] = []          # the plan changed: setpoint / expected saving before -> after, why
        self._plan_snap: dict | None = None         # the plan in force and what it saw (replan.snapshot)
        self.day_stats: dict[str, dict] = {}        # date -> the day in numbers (look back, day report)
        self.pred: dict[int, dict] = {}             # hour start -> room predicted for it 6 h and 1 h ahead
        self.plan_log: list[dict] = []              # per hour: everything the plan in force saw (replay a decision)
        self.plan_w_now: float | None = None        # the unit's output the last plan started from (kW)
        self.commit: stick.Commitment | None = None   # the plan held: its setpoints and what it expected (stick.py)
        self._watch = stick.Watch()
        self.plan_why: str | None = None            # why the plan held was made afresh (stick.why_plan)
        self.fallback: str | None = None            # "no_price": planned on one flat price; "schedule": comfort schedule
        self._fail_since: float | None = None       # planning has failed since (no price, room or weather)
        self._tariff_now: float | None = None       # the import price this hour, from the last tick (cost without a plan)
        self.unpriced_kwh = 0.0                     # heating electricity today without any known price
        self._heating_since: float | None = None    # the unit has been heating since (MIN_RUN_MIN)
        self.runs: list[list] = []                  # [start, end or None]: the unit's space heating runs, the last days
        self._airing_from: float | None = None      # the setpoint before Roost lowered it for an open window (contact)
        self.window = window.WindowWatch()          # airing: Roost waits and does not learn from those hours
        self.curve_advice = None                    # curve.CurveAdvice: the heating curve the house needs
        self.quatt_info: dict = {}                  # the unit as the Quatt entities show it (outdoor units, boiler)
        self.cost_today = 0.0
        self.kwh_today = 0.0
        self._care_init()
        self._cost_day: str | None = None
        self._last_tick: float | None = None
        self.pv_k: float | None = None              # kW of PV per kW/m² of radiation (learned)
        self.load_profile: list[float] | None = None
        self.battery = battery.BatteryHabits()      # how the home battery is charged (battery.py, learned nightly)
        self.health = Health()
        self._weather: dict[int, tuple] = {}
        self._weather_at = 0.0
        self._pump_hours: dict[int, dict] = {}      # the unit's hours: from the statistics, and counted live
        self._live = quatt.LiveHour()
        self._last_elec: float | None = None        # a meter reading (Weheat); a Quatt has no meter: it stays None
        self.live_hours: dict[int, dict] = {}       # seconds per state Roost counted itself, the last days (quatt.LIVE_KEEP_DAYS)
        self._weather_hist: dict[int, tuple] = {}
        self._planning = False
        self._learning = False
        self.importing = False
        self.check: dict = {}                       # nightly self-check (check.self_check)
        self.changes: list[dict] = []               # changes by hand while active: {"ts", "from", "to", "room"}
        self.building: dict | None = None           # opt-in BAG data: {"lat", "lon", "year", "area_m2", "walls"} (no address)
        # extra rooms (subentries of type "room"): the heat pump heats them too, Roost keeps their minimums
        self.rooms: list[rooms.Room] = [
            rooms.Room(id=sid, name=sub.title, sensor=sub.data["sensor"], kind=sub.data.get("kind", "other"),
                       minimum=_f(sub.data.get("minimum")), hour_from=_i(sub.data.get("hour_from")), hour_to=_i(sub.data.get("hour_to")))
            for sid, sub in getattr(entry, "subentries", {}).items() if sub.subentry_type == "room" and sub.data.get("sensor")]
        self.room_models: dict[str, rooms.RoomModel] = {}
        self.room_status: list[dict] = []
        self.suggestion: comfort.Suggestion | None = None
        # what Roost did and why, for a bug report (diagnostics): thermostat changes, changes by hand, mode, learning,
        # import, repairs, plans that could not be made, errors
        self.events: deque = deque(maxlen=EVENTS_KEPT)
        self._tasks: set[asyncio.Task] = set()
        self._epex: list[tuple[float, float, float]] = []   # built-in day-ahead prices (epex.py)
        self._epex_at: float | None = None
        self._need_epex = False                     # a price sensor without a forecast: estimate from day-ahead prices
        self._stop_unsub: Callable[[], None] | None = None
        self._last_reason_code: str | None = None
        self.ready: bool = False
        self.ready_missing: list[str] = []
        self.corr_kw, self.corr_n = 0.0, 0   # correction from the last hours (check.correction)
        self._acc_hour: int | None = None           # the current hour: seconds on hot water, heat for the house
        self._dhw_acc = 0.0
        self._heat_acc = 0.0
        self._elec_acc = 0.0                        # heating electricity in this hour (kWh) and its cost
        self._cost_acc = 0.0
        self._obs_acc = 0.0                         # seconds of this hour Roost saw (a restart: fewer)
        # per hour: mean room setpoint and the thermostat's own reading, from the thermostat entity (an on/off thermostat
        # may not pass its setpoint on; HA statistics keep no attributes)
        self.sp_hist: dict[int, list] = {}
        self._sp_acc = [0.0, 0.0, 0.0, 0.0]      # setpoint × s, s, reading × s, s

    # ------------------------------------------------------------ config
    @property
    def conf(self) -> dict:
        return {**DEFAULTS, **self.entry.data, **self.entry.options}

    @property
    def hybrid(self) -> bool:
        """A gas boiler next to the heat pump (history.is_hybrid)."""
        return history.is_hybrid(None, self.boiler_hours)

    def settings(self) -> planner.Settings:
        c = self.conf
        night = _f(c.get(CONF_BASELINE_NIGHT)) or 0.0
        above = float(c[CONF_MAX_ABOVE])
        if self.hybrid:
            above = min(above, HYBRID_MAX_ABOVE)    # a hybrid: a setpoint far above the room calls the gas boiler
        return planner.Settings(comfort=float(c[CONF_COMFORT]), day_min=float(c[CONF_DAY_MIN]), night_min=float(c[CONF_NIGHT_MIN]),
                                store_max=max(float(c[CONF_STORE_MAX]), float(c[CONF_COMFORT])), max_above_room=above,
                                sp_min=float(c.get(CONF_SP_MIN, c[CONF_NIGHT_MIN])),
                                baseline_night=night if night > 0 else None,
                                away_min=float(self.mem.away_min) if self.mem.away_min is not None else AWAY_MIN)

    def control_settings(self) -> control.ControlSettings:
        c = self.conf
        return control.ControlSettings(min_interval_min=float(c[CONF_MIN_INTERVAL]), pause_hours=float(c[CONF_PAUSE_HOURS]))

    def is_day(self, local: datetime) -> bool:
        return schedule.is_comfort(self.conf, local)

    # ------------------------------------------------------------ lifecycle
    async def async_start(self) -> None:
        data = await self._store.async_load() or {}
        hist = await self._hist_store.async_load() or {}
        self._resolve_quatt()
        prof = heatpump.profile_for(self.pump_name)
        self.mode = data.get("mode", "shadow")
        self.house = model.HouseModel.from_dict(data.get("house"))
        if data.get("pump"):
            self.pump = heatpump.HeatPumpModel.from_dict(data.get("pump"), prof)
            if heatpump.reset_old_pmax(self.pump, prof):
                self.event("pmax_reset", profile=prof)     # an earlier, too high starting line: learning raises it again
        else:
            self.pump = heatpump.HeatPumpModel.for_profile(prof)
            self.pump.alpha = round(self.pump.alpha + heatpump.EMITTER_COP.get(self.conf.get(CONF_EMITTER, "floor"), 0.0), 3)
        self.mem = control.ControlMemory.from_dict(data.get("control"))
        self.storage_e = float(data.get("storage_e", 0.0))
        self._age_storage(data.get("storage_at"), time.time())
        self.learn_info = data.get("learn", {})
        self.import_info = data.get("import", {})
        self.hour_log = data.get("hour_log", [])
        self.saving_days = data.get("saving_days", {})
        self.day_stats = data.get("day_stats") or {}
        self.pred = {int(k): v for k, v in (data.get("pred") or {}).items()}
        self.plan_log = data.get("plan_log") or []
        self.saving_detail = data.get("saving_detail") or {}
        self.day_contexts = data.get("day_contexts") or {}
        self.replayed_with = data.get("replayed_with")
        self.plan_changes = data.get("plan_changes") or []
        self._plan_snap = data.get("plan_snap")
        self.commit = stick.Commitment.from_dict(data.get("commit"))
        self._restore_acc(data.get("acc"), time.time())
        self.runs = [r for r in (data.get("runs") or []) if isinstance(r, list) and len(r) == 2]
        if self.runs and self.runs[-1][1] is None:
            self._heating_since = self.runs[-1][0]  # a run that went on over the restart
        self.window.hours = set(int(h) for h in (data.get("window_hours") or []))
        self.pv_k = data.get("pv_k")
        self.load_profile = data.get("load_profile")
        self.battery = battery.BatteryHabits.from_dict(data.get("battery"))
        today = data.get("today") or {}
        if today.get("day"):                # another day: the first tick closes it and starts today at zero
            self._cost_day, self.cost_today, self.kwh_today = today["day"], float(today.get("cost") or 0.0), float(today.get("kwh") or 0.0)
        self.price_seen = {e: {int(k): v for k, v in d.items()} for e, d in (data.get("price_seen") or {}).items()}
        self.check = data.get("check") or {}
        self.changes = data.get("changes") or []
        self.sp_hist = {int(k): v for k, v in (data.get("sp_hist") or {}).items()}
        self.room_models = {k: rooms.RoomModel.from_dict(v) for k, v in (data.get("room_models") or {}).items()}
        self.events.extend(data.get("events") or [])
        self.event("start", mode=self.mode)
        self.building = data.get("building") if self.conf.get(CONF_USE_BAG) else None
        self.curve_advice = curve.CurveAdvice.from_dict(data.get("curve"))
        self.quatt_info = data.get("quatt_info") or {}
        if self.house.source != "learned":
            self.house = model.HouseModel(**self.house_start(), source="building register" if building.prior(self.building) else "default")
        self.ready, self.ready_missing = check.readiness(self.check, None, winter=self.check.get("winter")) if self.check else (False, [])
        self._pump_hours = {int(k): v for k, v in (hist.get("pump") or {}).items()}
        # kept in the small store, saved all the time: the history file is only written by the import and at night
        self.live_hours = {int(k): v for k, v in (data.get("live_hours") or {}).items()}
        quatt.merge_hours(self._pump_hours, self.live_hours)
        self.boiler_hours = history.boiler_hours(self._pump_hours)
        self._weather_hist = {int(k): tuple(v) for k, v in (hist.get("weather") or {}).items()}
        self._unsubs.append(async_track_time_interval(self.hass, self._async_tick, timedelta(seconds=TICK_SECONDS)))
        self._unsubs.append(async_track_time_change(self.hass, self._async_nightly, hour=LEARN_HOUR, minute=LEARN_MINUTE, second=0))
        self._unsubs.append(async_track_time_change(self.hass, self._async_weekly, hour=8, minute=0, second=0))
        self._unsubs.append(async_track_state_change_event(self.hass, [self.conf[CONF_THERMOSTAT]], self._on_thermostat))
        self._stop_unsub = self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._on_ha_stop)
        self.spawn(self._async_first_run(), "first run", background=False)
        if data.get("replayed_with") != planner.REPLAY_VERSION:
            self.spawn(self._async_replay_kept_days(), "replay the days kept")

    async def _async_building(self) -> None:
        """Opt-in: the building register (BAG via PDOK) around the home location, once (again when the home moves).
        Only the construction year, the floor area and the directions of the outside walls are kept."""
        if not self.conf.get(CONF_USE_BAG):
            return
        lat, lon = round(self.hass.config.latitude, 5), round(self.hass.config.longitude, 5)
        if self.building and abs(self.building.get("lat", 0) - lat) < 1e-4 and abs(self.building.get("lon", 0) - lon) < 1e-4:
            return
        bb = building.bbox(lat, lon)
        session = async_get_clientsession(self.hass)
        try:
            got = {}
            for kind in ("pand", "verblijfsobject"):
                async with session.get(building.WFS.format(kind=kind, **bb), timeout=30) as r:
                    r.raise_for_status()
                    got[kind] = await r.json(content_type=None)
            b = await self.hass.async_add_executor_job(building.parse, got["pand"], got["verblijfsobject"], lat, lon)
        except Exception as err:  # noqa: BLE001 - optional: without it Roost starts from a generic house
            _LOGGER.info("Roost: building register not available: %s", err)
            return
        self.building = {**b, "lat": lat, "lon": lon} if b else {"lat": lat, "lon": lon, "none": True}
        if b and self.house.source != "learned" and building.prior(b):
            self.house = model.HouseModel(**self.house_start(), source="building register")
        await self.async_save()

    async def _async_first_run(self) -> None:
        await self._async_building()
        await self._async_seed_prices()
        await self._async_pump_info()                      # whether a gas boiler is there, before the first plan
        if not self.battery.at:
            await self._async_learn_battery()              # how the battery is charged, before the first plan
        await self._async_tick(None, force_plan=True)
        if self.conf.get(CONF_IMPORT_ON_SETUP) and not self.import_info.get("done"):
            self.spawn(self.async_import(IMPORT_DAYS), "import from the statistics")
        elif self.import_info.get("done") and self.import_info.get("version", 1) < quatt.IMPORT_VERSION:
            # imported by an older version that read the statistics differently: read them again (seconds)
            self.spawn(self.async_import(IMPORT_DAYS), "import from the statistics (newer version)")
        elif self.house.source != "learned":
            self.spawn(self.async_learn(), "first learning")

    def spawn(self, coro, name: str, background: bool = True) -> asyncio.Task:
        """A job of Roost's own (import, learning; background=False: the first run, which startup waits for): tied to
        the config entry, and cancelled when Roost unloads or Home Assistant stops, so nothing asks the executor for
        work after it has shut down. The import carries on after a restart from the last month it finished."""
        task = (self.entry.async_create_background_task(self.hass, coro, f"{DOMAIN} {name}") if background
                else self.entry.async_create_task(self.hass, coro, f"{DOMAIN} {name}"))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def _cancel_tasks(self) -> None:
        for task in list(self._tasks):
            task.cancel()

    @callback
    def _on_ha_stop(self, _event) -> None:
        self._stop_unsub = None                 # fired: nothing to remove any more
        self._cancel_tasks()
        self.hass.async_create_task(self.async_save(), f"{DOMAIN} save on stop")   # the events

    async def async_stop(self) -> None:
        self._cancel_tasks()
        if self._stop_unsub is not None:
            self._stop_unsub()
            self._stop_unsub = None
        for u in self._unsubs:
            u()
        self._unsubs.clear()
        await self.async_save()

    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb)

    def _notify(self) -> None:
        for cb in list(self._listeners):
            cb()

    async def async_save(self) -> None:
        await self._store.async_save({
            "mode": self.mode, "house": self.house.as_dict(), "pump": self.pump.as_dict(), "control": self.mem.as_dict(),
            "storage_e": round(self.storage_e, 3), "learn": self.learn_info, "import": self.import_info,
            "hour_log": self.hour_log[-HOUR_LOG_KEPT:], "saving_days": dict(sorted(self.saving_days.items())[-62:]),
            "day_stats": dict(sorted(self.day_stats.items())[-62:]),
            "window_hours": sorted(h for h in self.window.hours if h > time.time() - 400 * 86400),
            "pred": {str(k): v for k, v in self.pred.items() if k > time.time() - 7200},
            "plan_log": self.plan_log[-PLAN_LOG_KEPT:], "replayed_with": self.replayed_with,
            "saving_detail": dict(sorted(self.saving_detail.items())[-SAVING_DETAIL_DAYS:]),
            "day_contexts": dict(sorted(self.day_contexts.items())[-SAVING_DETAIL_DAYS - 1:]),
            "plan_changes": replan.prune(self.plan_changes, time.time()), "plan_snap": self._plan_snap,
            "commit": self.commit.as_dict() if self.commit else None, "runs": self.runs, "acc": self._acc_state(),
            "storage_at": time.time(),
            "pv_k": self.pv_k, "load_profile": self.load_profile, "battery": self.battery.as_dict(), "price_seen": self._price_seen_recent(),
            "today": {"day": self._cost_day, "cost": round(self.cost_today, 4), "kwh": round(self.kwh_today, 3)},
            "check": self.check, "changes": [c for c in self.changes if c["ts"] > time.time() - 30 * 86400],
            "building": self.building,
            "curve": self.curve_advice.as_dict() if self.curve_advice else None, "quatt_info": self.quatt_info,
            "sp_hist": {str(k): v for k, v in self.sp_hist.items() if k > time.time() - SP_HIST_DAYS * 86400},
            "live_hours": {str(k): v for k, v in self.live_hours.items() if k > time.time() - quatt.LIVE_KEEP_DAYS * 86400},
            "room_models": {k: v.as_dict() for k, v in self.room_models.items() if any(r.id == k for r in self.rooms)},
            "events": list(self.events)})

    async def _async_save_history(self) -> None:
        cut = time.time() - HISTORY_KEEP_DAYS * 86400      # thirteen months: learning uses a year
        self._pump_hours = {k: v for k, v in self._pump_hours.items() if k >= cut}
        self.boiler_hours = history.boiler_hours(self._pump_hours)
        self._weather_hist = {k: v for k, v in self._weather_hist.items() if k >= cut}
        await self._hist_store.async_save({"pump": {str(k): v for k, v in self._pump_hours.items()},
                                           "weather": {str(k): list(v) for k, v in self._weather_hist.items()}})

    def event(self, kind: str, **data: Any) -> None:
        """Remember what happened (kept: the last EVENTS_KEPT, also over restarts)."""
        self.events.append({"t": dt_util.now().isoformat(timespec="seconds"), "kind": kind, **data})

    async def async_set_mode(self, mode: str) -> None:
        if mode != self.mode:
            self.event("mode", old=self.mode, new=mode)
        was_active = self.mode == "active"
        self.mode = mode
        if was_active and mode != "active":
            await self._async_back_to_comfort(f"mode {mode}")
        self.mem.virtual_sp = None
        self._issue_ready()
        await self.async_save()
        await self._async_tick(None, force_plan=True)

    # ------------------------------------------------------------ reading
    def _state(self, eid: str | None) -> State | None:
        if not eid:
            return None
        st = self.hass.states.get(eid)
        return None if st is None or st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN) else st

    def _num(self, eid: str | None) -> float | None:
        st = self._state(eid)
        return _f(st.state) if st else None

    def _temp(self, eid: str | None) -> float | None:
        st = self._state(eid)
        v = _f(st.state) if st else None
        if v is not None and st.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfTemperature.FAHRENHEIT:
            v = (v - 32) * 5 / 9
        return v if v is not None and history.BAD_LOW < v < history.BAD_HIGH else None

    def _kw(self, eid: str | None) -> float | None:
        st = self._state(eid)
        v = _f(st.state) if st else None
        if v is None:
            return None
        u = (st.attributes.get(ATTR_UNIT_OF_MEASUREMENT) or "").lower()
        return v / 1000 if u == "w" else v

    def _sys_to_c(self, v: float | None) -> float | None:
        if v is None:
            return None
        return (v - 32) * 5 / 9 if self.hass.config.units.temperature_unit == UnitOfTemperature.FAHRENHEIT else v

    def _c_to_sys(self, v: float) -> float:
        return round(v * 9 / 5 + 32) if self.hass.config.units.temperature_unit == UnitOfTemperature.FAHRENHEIT else v

    def room(self) -> float | None:
        r = self._temp(self.conf.get(CONF_ROOM))
        if r is None:
            st = self._state(self.conf[CONF_THERMOSTAT])
            r = self._sys_to_c(_f(st.attributes.get("current_temperature"))) if st else None
        if r is None:
            r = self._temp(self.ent.get("thermostat_room"))
        return r

    def thermostat_sp(self) -> float | None:
        st = self._state(self.conf[CONF_THERMOSTAT])
        return self._sys_to_c(_f(st.attributes.get("temperature"))) if st else None

    def thermostat_reading(self) -> float | None:
        st = self._state(self.conf[CONF_THERMOSTAT])
        return self._sys_to_c(_f(st.attributes.get("current_temperature"))) if st else None

    # ------------------------------------------------------------ weather
    async def _async_weather(self) -> None:
        if self.conf.get(CONF_WEATHER_SOURCE) == "entity" and self.conf.get(CONF_WEATHER):
            await self._async_weather_entity()
            return
        if self._weather and time.time() - self._weather_at < WEATHER_MINUTES * 60:
            return
        url = om.FORECAST.format(lat=self.hass.config.latitude, lon=self.hass.config.longitude, past=92)
        try:
            async with async_get_clientsession(self.hass).get(url, timeout=30) as r:
                r.raise_for_status()
                self._weather = om.parse(await r.json())
            self._weather_at = time.time()
            self.sources["weather"] = "Open-Meteo"
        except Exception as err:  # noqa: BLE001
            # not str(err): an HTTP error holds the request URL, and with it the home location
            self.sources["weather"] = f"Open-Meteo unavailable: {f'HTTP {err.status}' if hasattr(err, 'status') else type(err).__name__}"

    async def _async_weather_entity(self) -> None:
        eid = self.conf[CONF_WEATHER]
        if self._weather and time.time() - self._weather_at < WEATHER_MINUTES * 60:
            return
        try:
            resp = await self.hass.services.async_call("weather", "get_forecasts", {ATTR_ENTITY_ID: eid, "type": "hourly"},
                                                       blocking=True, return_response=True)
            out = {}
            # the weather entity's own units (R12): a forecast in °F or a wind in m/s or mph is not in Home Assistant's units
            st = self.hass.states.get(eid)
            t_unit = st.attributes.get("temperature_unit") if st else None
            w_unit = st.attributes.get("wind_speed_unit") if st else None
            for x in (resp or {}).get(eid, {}).get("forecast", []):
                ts = series.to_ts(x.get("datetime"))
                t = self._unit_to(_f(x.get("temperature")), t_unit, "temperature") if t_unit else self._sys_to_c(_f(x.get("temperature")))
                if ts is None or t is None:
                    continue
                ts = int(ts - ts % 3600)
                cloud = _f(x.get("cloud_coverage"))
                wind = _f(x.get("wind_speed"))
                wind = self._unit_to(wind, w_unit, "speed") if w_unit else ((wind / 3.6) if wind is not None else None)
                out[ts] = (t, self._clear_sky(ts) * (1 - 0.75 * ((cloud or 0) / 100) ** 3.4), wind)
            self._weather.update(out)
            self._weather_at = time.time()
            self.sources["weather"] = eid
        except Exception as err:  # noqa: BLE001
            self.sources["weather"] = f"{eid} unavailable: {err}"

    @staticmethod
    def _unit_to(v: float | None, unit: str, kind: str) -> float | None:
        """A value in a source's own unit to °C or m/s (Home Assistant's converters); an unknown unit: not used."""
        if v is None:
            return None
        from homeassistant.util.unit_conversion import SpeedConverter, TemperatureConverter
        conv, to = (TemperatureConverter, "°C") if kind == "temperature" else (SpeedConverter, "m/s")
        try:
            return conv.convert(v, unit, to)
        except Exception:  # noqa: BLE001 - a unit Home Assistant does not know
            return None

    def _clear_sky(self, ts: float) -> float:
        import math
        loc = dt_util.as_local(datetime.fromtimestamp(ts + 1800, tz=timezone.utc))
        decl = 23.44 * math.sin(math.radians(360 / 365 * (loc.timetuple().tm_yday - 81)))
        lat = math.radians(self.hass.config.latitude)
        ha = math.radians(15 * (loc.hour + loc.minute / 60 - 12.5))
        s = math.sin(lat) * math.sin(math.radians(decl)) + math.cos(lat) * math.cos(math.radians(decl)) * math.cos(ha)
        return max(0.0, 0.9 * s)

    # ------------------------------------------------------------ energy value

    def _rooms_ahead(self, hours: list[planner.HourIn]) -> tuple[list[dict], list[dict]]:
        """The extra rooms for the planner (model, temperature now, minimum, hours it holds) and for the card."""
        c = self.conf
        plan_in, meta = [], []
        for r in self.rooms:
            st = self._state(r.sensor)
            T = self._sys_to_c(_f(st.state)) if st else None
            lo, a, b = r.settings(int(c[CONF_DAY_FROM]), int(c[CONF_DAY_TO]))
            m = self.room_models.get(r.id) or rooms.RoomModel()
            if T is None:
                # not read now: no minimum to plan for, but it stays in the status (and the saving is not whole-house)
                meta.append({"id": r.id, "name": r.name, "kind": r.kind, "temperature": None, "minimum": lo, "from": a, "to": b,
                             "active_now": False, "model": m.source, "model_error": m.error, "available": False, "expected": []})
                continue
            inherits = r.hour_from is None and rooms.KINDS.get(r.kind, rooms.KINDS["other"])["from"] is None
            # a room that keeps the house's comfort hours follows the weekly comfort periods too
            act = [h.day if inherits else rooms.active(h.hour, a, b) for h in hours]
            plan_in.append({"model": m, "T": T, "min": lo, "active": act})
            meta.append({"id": r.id, "name": r.name, "kind": r.kind, "temperature": round(T, 1), "minimum": lo, "from": a, "to": b,
                         "active_now": act[0] if act else False, "model": m.source, "model_error": m.error})
        return plan_in, meta

    async def _async_learn_rooms(self, rows: list[model.HourRow]) -> None:
        """Per extra room: its model from the hourly means of its sensor, and a repair when it stays too cold."""
        if not self.rooms:
            return
        from .learning import async_hourly_means
        means = await async_hourly_means(self, [r.sensor for r in self.rooms], days=60)
        idx = {r.ts: r for r in rows}
        c = self.conf
        for r in self.rooms:
            m = means.get(r.sensor) or {}
            samples = [(m[t], m[t + 3600], idx[t].Q, idx[t].T_out, idx[t].T) for t in sorted(m) if t + 3600 in m and t in idx]
            learned = await self.hass.async_add_executor_job(rooms.learn, samples)
            if learned:
                self.room_models[r.id] = learned
            lo, a, b = r.settings(int(c[CONF_DAY_FROM]), int(c[CONF_DAY_TO]))
            since = time.time() - 3 * 86400
            log = []
            for t in sorted(x for x in m if x >= since):
                loc = dt_util.as_local(datetime.fromtimestamp(t, tz=timezone.utc))
                log.append((loc.date().isoformat(), rooms.active(loc.hour, a, b), m[t], lo))
            self._issue(f"room_cold_{r.id}", rooms.too_cold(log), translation_key="room_cold",
                        placeholders={"room": r.name, "minimum": f"{lo:g}", "hours": f"{a}:00–{b}:00"})

    def _note_no_plan(self) -> None:
        if self.reason.code != self._last_reason_code:
            self._last_reason_code = self.reason.code
            self.event("no_plan", reason=self.reason.code, sources=dict(self.sources))

    def house_start(self) -> dict:
        """Starting values for the house model: heat emitter and (opt-in) the building register."""
        return model.starting_values(self.conf.get(CONF_EMITTER, "floor"), building.prior(self.building))

    def sun_on_house(self, ts: int, wx: tuple) -> float:
        """Radiation driving the solar gain in this hour, for the facade the house model learned (sun.effective)."""
        return sun.effective(ts, wx, self.hass.config.latitude, self.hass.config.longitude, self.house.sun_facade, self.house.sun_vertical)

    def local_hour(self, ts: int) -> int:
        return dt_util.as_local(datetime.fromtimestamp(ts, tz=timezone.utc)).hour



    # ------------------------------------------------------------ the run
    async def _async_tick(self, _now: datetime | None, force_plan: bool | str = False) -> None:
        now = dt_util.utcnow()
        t = now.timestamp()
        try:
            if not self.ent:
                self._resolve_quatt()
            await self._async_weather()
            if self.conf.get(CONF_PRICE_MODE) == "epex" or self._need_epex:
                await self._async_epex(now)
            self._watch_window(t)
            self._track_storage(t)
            self._track_hour(t)
            self._track_live(t)
            self._watch_thermostat(t)
            self._count_cost(now)
            self._check_health(t)
            heating = self.pump_state() == "heating"
            self._track_runs(t, heating)
            self._heating_since = (self._heating_since or t) if heating else None
            e = self._energy(now, stick.HORIZON_H)
            self._tariff_now = e[0].import_price[0] if e else None
            why = self._why_plan(now, e, "forced" if force_plan is True else (force_plan or None))
            # a plan made afresh only for a reason (stick.py); otherwise the plan held is worked out again for the new
            # hour; without a plan, try again every PLAN_MINUTES
            due = (why is not None or self.plan_at is None or int(t // 3600) != int(self.plan_at // 3600)
                   or (self.plan is None and t - self.plan_at >= PLAN_MINUTES * 60))
            if due and not self._planning:
                await self._async_plan(now, why, e)
            self._log_hour(now)
            await self._async_control(t)
        except Exception as err:  # noqa: BLE001 - one bad run must not stop the integration
            _LOGGER.exception("Roost run failed")
            self.event("error", where="run", error=repr(err)[:200], trace=traceback.format_exc(limit=4)[-800:])
        self._last_tick = t
        self._notify()

    def _age_storage(self, saved_at: float | None, t: float) -> None:
        """Heat in the floor after Home Assistant was down (R19): it went on being released to the room meanwhile.
        Whether the unit heated is not known, so this is the lower estimate; a short restart changes nearly nothing."""
        if not saved_at or t <= saved_at:
            return
        hours = min(12.0, (t - saved_at) / 3600)
        lag = max(0.0, self.house.lag)
        keep = (lag / (1 + lag)) ** hours if lag > 0 else 0.0
        before = self.storage_e
        self.storage_e = max(0.0, self.storage_e * keep)
        if hours >= 0.25 and before - self.storage_e >= 0.05:
            self.event("storage_aged", hours=round(hours, 2), before=round(before, 2), after=round(self.storage_e, 2))

    def _track_storage(self, t: float) -> None:
        """Heat in the floor/water: + heat the pump delivers for space heating, − the learned release to the room."""
        if self._last_tick is None:
            return
        dt_h = min(0.5, max(0.0, (t - self._last_tick) / 3600))
        q = 0.0
        if self.pump_state() == "heating":
            q = max(0.0, (self._kw(self.ent.get("power_out")) or 0.0))
        lag = max(0.0, self.house.lag)
        keep = (lag / (1 + lag)) ** dt_h if lag > 0 else 0.0
        self.storage_e = max(0.0, min(20.0, (self.storage_e + q * dt_h) * keep))

    def _count_cost(self, now: datetime) -> None:
        day = dt_util.as_local(now).date().isoformat()
        if self._cost_day != day:
            if self._cost_day is not None:
                self.spawn(self._async_close_day(self._cost_day), "close the day", background=False)
            self._cost_day, self.cost_today, self.kwh_today = day, 0.0, 0.0
            self.unpriced_kwh = 0.0
        # the Quatt has no energy meter: its electricity is the power integrated over the time since the last run, while it
        # heats (as a heat pump's own meter for heating counts it: not the standby in between); a power reading that is
        # briefly unavailable adds nothing
        t = now.timestamp()
        kw = self._kw(self.ent.get("power_in")) if self.pump_state() == "heating" else None
        if kw is not None and self._last_tick is not None and 0 < t - self._last_tick <= 600:
            d = max(0.0, kw) * (t - self._last_tick) / 3600
            h = self.plan_hour(now)
            # no plan: the published price of this hour; none known: counted as energy without a price, not as free
            price = h.p_grid if h is not None else self._tariff_now
            self.kwh_today += d
            self._elec_acc += d
            if price is None:
                self.unpriced_kwh += d
            else:
                self.cost_today += d * price
                self._cost_acc += d * price

    def _track_runs(self, t: float, heating: bool) -> None:
        """The unit's space heating runs (start, end): how often it starts and how long it runs, for the card."""
        if heating and (not self.runs or self.runs[-1][1] is not None):
            self.runs.append([round(t), None])
        elif not heating and self.runs and self.runs[-1][1] is None:
            self.runs[-1][1] = round(t)
        self.runs = [r for r in self.runs if (r[1] or t) > t - 3 * 86400]

    def run_stats(self, t: float) -> dict:
        """Per local day (today, yesterday): runs started and their mean length in minutes (a run going on counts to now)."""
        today = dt_util.as_local(datetime.fromtimestamp(t, tz=timezone.utc)).date()
        out = {}
        for key, day in (("today", today), ("yesterday", today - timedelta(days=1))):
            mine = [r for r in self.runs if dt_util.as_local(datetime.fromtimestamp(r[0], tz=timezone.utc)).date() == day]
            mins = [((r[1] or t) - r[0]) / 60 for r in mine]
            out[key] = {"starts": len(mine), "minutes": round(sum(mins) / len(mins)) if mins else None}
        out["heating"] = bool(self.runs and self.runs[-1][1] is None)
        return out

    def plan_hour(self, now: datetime):
        """Input for this UTC hour, including before a new plan is ready at the hour boundary."""
        if self.plan_at is None:
            return None
        i = int(now.timestamp() // 3600) - int(self.plan_at // 3600)
        return self.plan_hours[i] if 0 <= i < len(self.plan_hours) else None

    def _hours_ahead(self, now: datetime, prices: list[value.HourPrices], tariff: list[float]) -> list[planner.HourIn]:
        base = int(now.timestamp() // 3600 * 3600)
        out = []
        last = None
        for i, p in enumerate(prices):
            wx = self._weather.get(base + i * 3600) or last
            if wx is None:
                t_out = self._num(self.ent.get("outdoor"))
                if t_out is None:
                    return []
                wx = (t_out - self.pump.bias, 0.0, 3.5)
            last = wx
            loc = dt_util.as_local(datetime.fromtimestamp(base + i * 3600, tz=timezone.utc))
            dhw = self.pump.dhw_share(loc.weekday(), loc.hour)
            if i == 0 and self.pump_state() in DHW_STATES:
                dhw = max(dhw, 0.5)                     # making hot water right now
            rad = self.sun_on_house(base + i * 3600, wx)
            mask = None
            if self.conf.get(schedule.ENABLED):
                mask = tuple(self.is_day(dt_util.as_local(datetime.fromtimestamp(base+i*3600+q*900, tz=timezone.utc)))
                             for q in range(4))
            out.append(planner.HourIn(t_out=wx[0], wind=wx[2] if wx[2] is not None else 3.5, rad=rad,
                                      p_grid=p.p_grid, p_own=p.p_own, own_kw=p.own_kw, day=any(mask) if mask else self.is_day(loc),
                                      comfort_mask=mask, hour=loc.hour, dhw=dhw,
                                      extra_kw=check.fade(self.corr_kw, i), away=self.is_away(base + i * 3600),
                                      p_imp=tariff[i] if i < len(tariff) else None))
        return out

    def _why_plan(self, now: datetime, e, force: str | None) -> str | None:
        """Why to make the plan afresh now (stick.why_plan), from what Roost measures and the forecasts now."""
        t = now.timestamp()
        c = self.commit
        tariff = list(e[0].import_price) if e else None
        base = int(t // 3600 * 3600)
        t_out, rad = [], []
        for i in range(stick.WEATHER_H):
            wx = self._weather.get(base + i * 3600)
            if wx is None:
                break
            t_out.append(wx[0])
            rad.append(self.sun_on_house(base + i * 3600, wx))
        pv = self._pv_forecast(t, stick.WEATHER_H) if e and self.conf.get(CONF_PV_FORECAST) else None
        pv_now = self._watch.feed_pv(t, self._kw(self.conf.get(CONF_PV_POWER))) if self.conf.get(CONF_PV_FORECAST) else None
        coarse = window.reading_step(self.window.changes) >= 0.3
        why = stick.why_plan(c, t, room=self.room(), coarse=coarse, tariff=tariff, t_out=t_out, rad=rad, pv=pv,
                             pv_now_kw=pv_now, watch=self._watch, force=force)
        if why is None and c is not None and self.fallback == "no_price" and e:
            why = "prices"                                  # prices are back
        return why

    def _flat_energy(self, now: datetime, hours: int = 24):
        """No price: one flat price for every hour (the last known import price), so Roost still plans for comfort and
        the weather, without moving heat to cheaper hours."""
        known = [v for d in self.price_seen.values() for _, v in sorted(d.items())[-1:]]
        p = self.plan_tariff[0] if self.plan_tariff else (known[0] if known else 0.25)
        inp = value.EnergyInputs(import_price=[p] * hours, export_price=[p] * hours)
        ev = value.EnergyValue(value=[p] * hours, source=[value.SOURCE_GRID] * hours, surplus_kwh=[0.0] * hours)
        return inp, ev

    def _plan_failed(self, code: str, t: float) -> None:
        """No plan could be made. The plan held stays for its current hour for FALLBACK_MIN; after that, the comfort
        schedule (fallback "schedule") rather than whatever the thermostat was last given (a high setpoint to store heat,
        or a low one in an expensive hour)."""
        self.reason = Reason(code)
        self._fail_since = self._fail_since or t
        self._note_no_plan()
        if t - self._fail_since >= FALLBACK_MIN * 60:
            self.plan, self.plan_hours, self.plan_tariff, self.plan_guess = None, [], [], []
            self.commit = None
            if self.fallback != "schedule":
                self.event("fallback", to="schedule", why=code)
            self.fallback = "schedule"
            self.reason = Reason("fallback_schedule")
        self._issue("fallback", bool(self.fallback and t - self._fail_since >= FALLBACK_NOTICE_H * 3600),
                    placeholders={"why": code})

    def fallback_sp(self, t: float) -> float:
        """The comfort schedule: comfort in the comfort hours, the night minimum outside them, the away minimum away."""
        if self.is_away(t):
            return self.settings().away_min
        if self.is_day(dt_util.as_local(datetime.fromtimestamp(t, tz=timezone.utc))):
            return float(self.conf[CONF_COMFORT])
        return float(self.conf[CONF_NIGHT_MIN])

    def planned_sp(self, t: float) -> float | None:
        """The setpoint for now: the plan's for this hour, or the fallback."""
        if self.plan is not None and self.plan_at is not None:
            i = int(t // 3600) - int(self.plan_at // 3600)
            if 0 <= i < len(self.plan.hours):
                return self.plan.hours[i].sp
        if self.fallback == "schedule":
            return self.fallback_sp(t)
        return None

    async def _async_plan(self, now: datetime, why: str | None = None, e=...) -> None:
        self._planning = True
        try:
            t = now.timestamp()
            if e is ...:
                e = self._energy(now, 36)             # up to 36 h, bounded by published tariffs
            room = self.room()
            fallback = None
            if e is None and room is not None and self._fail_since and t - self._fail_since >= FALLBACK_MIN * 60:
                e, fallback = self._flat_energy(now), "no_price"
                why = why or "fallback"
            if e is None or room is None:
                self._plan_failed("no_price" if e is None else "no_room", t)
                return
            inp, ev = e
            prices = value.planner_prices(inp, ev)
            self.corr_kw, self.corr_n = check.correction(self.hour_log, self.house, self.pump, now.timestamp())
            hours = self._hours_ahead(now, prices, inp.import_price)
            if not hours:
                self._plan_failed("no_weather", t)
                return
            s = self.settings()
            w_now = self._kw(self.ent.get("power_out")) if self.pump_state() == "heating" else 0.0
            room_in, room_meta = self._rooms_ahead(hours)
            mode = self.conf.get(CONF_PRICE_MODE)
            guess = [] if mode == "fixed" else list(self._price_guess.get("epex_import" if mode == "epex" else self.conf.get(CONF_IMPORT_PRICE)) or [])[:len(hours)]
            sp_now = self.thermostat_sp() if self.thermostat_sp() is not None else self.mem.last_sp
            # the plan held: keep its setpoints and work out what they give now; a reason: plan afresh
            fixed = None
            if why is None and self.commit is not None and (self.commit.fallback or None) == fallback:
                fixed = self.commit.setpoints(t)
                if not fixed:
                    why = "horizon"
            elif why is None:
                why = "first"
            p = await self.hass.async_add_executor_job(partial(planner.plan, self.house, self.pump, s, hours, room,
                                                               self.storage_e, sp_now, 24, w_now, room_in,
                                                               fixed=fixed or None, extra_rooms=len(self.rooms)))
            if not fixed:
                self.commit = stick.Commitment(at=t, hour0=int(t // 3600 * 3600), sp=[x.sp for x in p.hours], room0=room,
                                               t_end=[round(x.t_end, 3) for x in p.hours], t_out=[h.t_out for h in hours],
                                               rad=[h.rad for h in hours], tariff=list(inp.import_price),
                                               pv=list(inp.pv_kwh) if inp.pv_kwh and self.conf.get(CONF_PV_FORECAST) else None,
                                               fallback=fallback)
                self._watch.room_off = 0
                self.plan_why = why
                self.event("plan", why=why, sp=[x.sp for x in p.hours[:6]], fallback=fallback)
            if self.fallback != fallback:
                if fallback:
                    self.event("fallback", to=fallback, why="no_price")
                self.fallback = fallback
            if not fallback:
                self._fail_since = None
                self._issue("fallback", False)
            self.plan_on_guess = False
            if len(p.hours) < 24:
                # A partial tariff horizon is usable for steering, not a complete next-24-hour saving estimate.
                quality = {**p.breakdown["quality"], "valid": False, "status": "incomplete_forecast",
                           "reasons": p.breakdown["quality"]["reasons"] + ["incomplete_forecast"]}
                p.breakdown = savings.publish(p.breakdown, quality)
            if fallback:
                quality = {**p.breakdown["quality"], "valid": False, "status": "fallback",
                           "reasons": p.breakdown["quality"]["reasons"] + ["no_price"]}
                p.breakdown = savings.publish(p.breakdown, quality)
            seen = [m for m in room_meta if m.get("available", True)]
            self.room_status = [{**meta, "expected": temps[:24]} for meta, temps in zip(seen, p.rooms)] + \
                               [m for m in room_meta if not m.get("available", True)]
            self.plan, self.plan_hours, self.plan_at, self.plan_w_now = p, hours, now.timestamp(), w_now
            self.plan_tariff = list(inp.import_price)
            self.plan_guess = guess
            self._remember_prediction(now, p)
            try:
                snap = replan.snapshot(now.timestamp(), int(now.timestamp() // 3600 * 3600), p, hours, inp.import_price, guess, room,
                                       self.corr_kw, {**vars(s), "comfort_schedule": schedule.context(self.conf)}, self.plan_on_guess)
                line = replan.compare(self._plan_snap, snap, room)
                if line:
                    self.plan_changes = replan.prune(self.plan_changes + [line], now.timestamp())
                self._plan_snap = snap
            except Exception as err:  # noqa: BLE001 - the change log must never stop planning and steering
                _LOGGER.debug("plan change log: %s", err)
                self._plan_snap = None
            self.reason = planner.explain(p, hours, room, s, self.pump, self.house, self.conf.get(CONF_EMITTER, "floor") == "floor")
            if fallback:
                self.reason = Reason("fallback_no_price")
            self._last_reason_code = None
        finally:
            self._planning = False

    async def _async_write(self, sp: float) -> bool:
        """Set the thermostat (Roost's own context, so it is not taken for a change by hand)."""
        ctx = Context()
        self._contexts[ctx.id] = time.time()
        await self.hass.services.async_call("climate", "set_temperature",
                                            {ATTR_ENTITY_ID: self.conf[CONF_THERMOSTAT], "temperature": self._c_to_sys(sp)},
                                            blocking=True, context=ctx)
        return True

    async def _async_airing(self, t: float) -> None:
        """A window/door sensor says open: the thermostat to the lowest setpoint so the unit stops heating the outdoors
        (not for a fall of the room alone: that can be a false alarm). Back to the plan when it closes (_watch_window)."""
        self.reason = Reason("airing")
        cur = self.thermostat_sp()
        low = float(self.conf.get(CONF_SP_MIN, self.conf[CONF_NIGHT_MIN]))
        paused = bool(self.mem.pause_until and t < self.mem.pause_until)
        if (self.mode == "active" and not paused and self._airing_from is None and cur is not None and cur > low + 0.01
                and self.thermostat_reachable()):
            try:
                await self._async_write(low)
                self._airing_from = cur
                self.event("airing", old=cur, new=low)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Roost could not lower the thermostat for an open window: %s", err)
                self.event("set_failed", new=low, error=str(err)[:200])
        self.decision = control.Decision(None, Reason("airing"), self.thermostat_sp())

    async def _async_control(self, t: float) -> None:
        if self.window.active():
            if self.window.via == "contact":
                await self._async_airing(t)
                return
            # airing seen from the room alone: changing the thermostat now would heat the outdoors; wait until the room is back
            self.reason = Reason("window_open")
            self.decision = control.Decision(None, Reason("window_open"), self.thermostat_sp())
            return
        planned = self.planned_sp(t)
        if self.mode == "off" or planned is None:
            self.decision = control.Decision(None, Reason("off") if self.mode == "off" else self.reason, self.thermostat_sp())
            return
        if self.mode == "active" and not self.thermostat_reachable():
            self.decision = control.Decision(None, Reason("no_plan"), None)     # unreachable: leave it alone (a notice follows)
            return
        hard = (self.settings().away_min if self.is_away(t) else float(self.conf[CONF_DAY_MIN]) if self.is_day(dt_util.as_local(datetime.fromtimestamp(t, tz=timezone.utc)))
                else float(self.conf[CONF_NIGHT_MIN]))
        current = self.thermostat_sp() if self.mode == "active" or self.mem.virtual_sp is None else self.mem.virtual_sp
        room = self.room()
        if (self._heating_since is not None and t - self._heating_since < MIN_RUN_MIN * 60 and current is not None
                and planned < current - 0.01 and (room is None or room < self.settings().store_max)
                and not (self.mem.pause_until and t < self.mem.pause_until)):
            # the unit just started: a short run wears it and wastes the warm-up; lower once it has run a while
            mins = round(MIN_RUN_MIN - (t - self._heating_since) / 60)
            self.decision = control.Decision(None, Reason("min_run", {"min": mins}), current)
            return
        before = (self.mem.last_write, self.mem.last_sp)
        d = control.decide(t, planned, self.thermostat_sp(), room, hard,
                           self.mem, self.control_settings(), self.mode == "active")
        self.decision = d
        if d.setpoint is not None and self.mode == "active":
            old = self.thermostat_sp()
            try:
                await self._async_write(d.setpoint)
                self.event("set", old=old, new=d.setpoint, why=d.why.code, reason=self.reason.code, args=dict(self.reason.args),
                           room=room)
                self._set_result(True)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Roost could not set the thermostat: %s", err)
                self.event("set_failed", new=d.setpoint, error=str(err)[:200])
                self._set_result(False, str(err))
                # not applied: the change interval does not start; try again soon, later after each failure
                interval = self.control_settings().min_interval_min
                retry = min(interval, 5 * 2 ** max(0, self._set_fails - 1))
                self.mem.last_write = t - (interval - retry) * 60
                self.mem.last_sp = before[1]
                self.decision = control.Decision(None, Reason("set_failed", {"min": round(retry)}), old)
        if d.setpoint is not None:
            await self.async_save()

    @callback
    def _on_thermostat(self, event: Event) -> None:
        old, new = event.data.get("old_state"), event.data.get("new_state")
        if old is None or new is None or event.context.id in self._contexts or self.mode != "active":
            return
        a, b = _f(old.attributes.get("temperature")), _f(new.attributes.get("temperature"))
        if a is None or b is None or abs(a - b) < 0.05:
            return
        # our own change coming back (a thermostat may report it without our context); a change that carries a user
        # is that user's, also right after ours (R20)
        if self.mem.last_write and time.time() - self.mem.last_write < 60 and not event.context.user_id:
            return
        self.mem.pause_until = time.time() + self.control_settings().pause_hours * 3600
        room = self.room()
        self.changes.append({"ts": round(time.time()), "from": a, "to": b, "room": round(room, 2) if room is not None else None})
        self.event("by_hand", old=a, new=b, room=room, pause_h=self.control_settings().pause_hours,
                   context_user=bool(event.context.user_id), context_parent=bool(event.context.parent_id))
        self.hass.async_create_task(self.async_save())
        self._notify()

    # ------------------------------------------------------------ health (repairs)

    def _track_hour(self, t: float) -> None:
        """Per hour: seconds on hot water (an hour on hot water is not a model error) and the heat delivered to the house
        (where the unit's output starts in the next hour), for the correction."""
        hour = int(t // 3600 * 3600)
        if self._acc_hour != hour:
            if self._acc_hour is not None:
                self._close_hour(self._acc_hour, self.room())
            self._acc_hour, self._dhw_acc, self._heat_acc = hour, 0.0, 0.0
            self._elec_acc = self._cost_acc = self._obs_acc = 0.0
            self._sp_acc = [0.0, 0.0, 0.0, 0.0]
            self._sources_reset()
        if self._last_tick is None:
            return
        dt = min(600.0, max(0.0, t - self._last_tick))
        self._obs_acc += dt
        self._sources_tick(dt)
        sp, reading = self.thermostat_sp(), self.thermostat_reading()
        if sp is not None:
            self._sp_acc[0] += sp * dt
            self._sp_acc[1] += dt
        if reading is not None:
            self._sp_acc[2] += reading * dt
            self._sp_acc[3] += dt
        state = self.pump_state()
        if state in DHW_STATES:
            self._dhw_acc += dt
        elif state == "heating":
            self._heat_acc += max(0.0, self._kw(self.ent.get("power_out")) or 0.0) * dt / 3600

    def _close_hour(self, hour: int, room: float | None, partial: bool = False) -> None:
        """The hour's measurements into its log entry: heating electricity, its cost, heat, hot water, the mean setpoint,
        and how many seconds of it Roost saw (a restart in the hour: `obs` short, so the day is not taken as complete)."""
        for e in reversed(self.hour_log[-3:]):
            if e["ts"] == hour:
                e["dhw"] = round(min(1.0, self._dhw_acc / 3600), 2)
                e["q"] = round(self._heat_acc, 2)
                e["e"] = round(self._elec_acc, 3)
                e["cost"] = round(self._cost_acc, 4)
                e["obs"] = round(self._obs_acc)
                if room is not None or "T_end" not in e:
                    e["T_end"] = room
                if self._sp_acc[1] >= 1800:
                    e["sp_mean"] = round(self._sp_acc[0] / self._sp_acc[1], 2)
                if partial:
                    e["partial"] = True
                self._sources_close(e)
        a = self._sp_acc
        if a[1] >= 1800:                      # at least half the hour seen
            self.sp_hist[hour] = [round(a[0] / a[1], 2), round(a[2] / a[3], 2) if a[3] >= 1800 else None]

    def _acc_state(self) -> dict:
        """The hour in progress, saved with the rest: a restart within the hour goes on counting from here (R18)."""
        return {"hour": self._acc_hour, "dhw": self._dhw_acc, "heat": self._heat_acc, "elec": self._elec_acc,
                "cost": self._cost_acc, "obs": self._obs_acc, "sp": list(self._sp_acc), "src": list(self._src_acc),
                "last_elec": self._last_elec, "live": self._live.state(), "at": time.time()}

    def _restore_acc(self, d: dict | None, t: float) -> None:
        """Back after a restart. The same hour: go on counting, from the meter reading Roost had. A later hour: the hour
        that was going on is closed with what was seen of it (marked partial); the meter starts afresh, as the use while
        Home Assistant was down cannot be put in an hour."""
        if not d or d.get("hour") is None:
            return
        self._acc_hour = int(d["hour"])
        self._dhw_acc, self._heat_acc = float(d.get("dhw") or 0.0), float(d.get("heat") or 0.0)
        self._elec_acc, self._cost_acc = float(d.get("elec") or 0.0), float(d.get("cost") or 0.0)
        self._obs_acc = float(d.get("obs") or 0.0)
        self._sp_acc = list(d.get("sp") or [0.0, 0.0, 0.0, 0.0])
        self._src_acc = list(d.get("src") or [0.0, 0.0, 0.0])
        if self._acc_hour == int(t // 3600 * 3600):
            self._last_elec = d.get("last_elec")
            self._live.restore(d.get("live"))       # the seconds of heating counted in this hour so far (Quatt)
        else:
            self._close_hour(self._acc_hour, None, partial=True)
            self._acc_hour = None

    def _dhw_samples(self, rows: list[model.HourRow]) -> list[tuple[int, int, float]]:
        """(local weekday, local hour, share on hot water) of the last weeks (a Quatt makes no hot water: all zero)."""
        since = time.time() - DHW_WEEKS * 7 * 86400
        src = {t: v["dhw_s"] for t, v in self._pump_hours.items() if t >= since and "dhw_s" in v}
        if len(src) < 7 * 24:
            src = {r.ts: r.dhw_s for r in rows if r.ts >= since}
        out = []
        for t, secs in src.items():
            loc = dt_util.as_local(datetime.fromtimestamp(t, tz=timezone.utc))
            out.append((loc.weekday(), loc.hour, secs / 3600))
        return out



    # ------------------------------------------------------------ services
    async def async_pause(self, hours: float) -> None:
        self.event("pause", hours=hours)
        self.mem.pause_until = time.time() + hours * 3600
        await self.async_save()
        self._notify()

    async def async_resume(self) -> None:
        self.event("resume")
        self.mem.pause_until = None
        self.mem.last_write = None
        await self.async_save()
        await self._async_tick(None, force_plan=True)

    # ------------------------------------------------------------ learning
    async def _async_nightly(self, _now: datetime) -> None:
        await self._async_refresh_pump()
        await self._async_learn_battery()
        await self.async_learn()

    async def _async_learn_battery(self) -> None:
        """How the home battery is charged (from the grid, in which hours, how full) and the charge it stops at."""
        from .learning import async_battery
        try:
            got = await async_battery(self)
        except Exception as err:  # noqa: BLE001 - keep what was learned before
            _LOGGER.debug("Roost: battery habits not learned: %s", err)
            return
        if got is None:
            return
        was = self.battery.charges_from_grid
        got.at = dt_util.now().isoformat(timespec="seconds")
        self.battery = got
        if got.charges_from_grid != was:
            self.event("battery", grid_charging=got.charges_from_grid, hours=got.charge_hours, kwh_day=got.grid_kwh_day)

    async def async_learn(self) -> None:
        if self._learning:
            return
        self._learning = True
        try:
            from .learning import async_rows
            if not self._weather:
                await self._async_weather()           # just after a start the forecast service may not have answered yet
            rows, extra = await async_rows(self)
            if model.stale(rows, time.time()):
                # without the newest hours the test days would be weeks old (seen 18-10-2026: the last row in July after
                # a restart without weather, and a summer model taken in October): wait for the next run
                newest = max((r.ts for r in rows), default=None)
                self.event("learn_skipped", reason="no recent hours",
                           newest=datetime.fromtimestamp(newest, tz=timezone.utc).isoformat() if newest else None)
                return
            # airing: those hours look like a house that suddenly loses much more heat; leave them out
            rows = [r for r in rows if r.ts not in self.window.hours]
            # hours without the setpoint from the unit (an on/off thermostat): Roost's own record of the thermostat
            rows = [replace(r, sp=self.sp_hist[r.ts][0] if r.sp is None else r.sp,
                            T_th=self.sp_hist[r.ts][1] if r.T_th is None else r.T_th) if r.ts in self.sp_hist else r for r in rows]
            wx_all = {**self._weather_hist, **self._weather}
            lat, lon = self.hass.config.latitude, self.hass.config.longitude

            def eff(ts: int, facade: float, vertical: float) -> float:
                wx = wx_all.get(ts)
                return sun.effective(ts, wx, lat, lon, facade, vertical) if wx else 0.0
            hours = {r.ts: self.local_hour(r.ts) for r in rows}
            house = await self.hass.async_add_executor_job(model.learn, rows, self.house, eff, hours.__getitem__,
                                                           self.house_start(), building.facades(self.building, model.FACADES))
            # from here on the rows carry the sun on the learned facade and their local hour
            hm = house.model
            rows = [replace(r, rad=eff(r.ts, hm.sun_facade, hm.sun_vertical) if hm.sun_vertical > 0 else r.rad, hour=hours[r.ts]) for r in rows]
            pump, note = await self.hass.async_add_executor_job(heatpump.learn, rows, self.pump)
            pump, note_r = await self.hass.async_add_executor_job(response.learn, rows, house.model, pump)
            note = "; ".join(x for x in (note, note_r) if x)
            samples = self._dhw_samples(rows)
            prof = response.dhw_profile(samples)
            if prof:
                pump.dhw, pump.dhw_weeks = prof, round(len(samples) / 168, 1)
            # check the new pair before it is used: a failure from here on keeps the models, check and readiness it had
            chk = await self.hass.async_add_executor_job(check.self_check, rows, house.model, pump)
            if chk.get("heating_hours", 0) < check.READY_HEATING_HOURS:      # mild weather: the last heating weeks decide
                winter = await self.hass.async_add_executor_job(check.winter_check, rows, house.model, pump)
                if winter:
                    chk["winter"] = winter
            chk["at"] = dt_util.now().isoformat(timespec="seconds")
            self.house, self.pump, self.check = house.model, pump, chk
            lever = not (self.pump.resp_source == "learned" and self.pump.k is not None and self.pump.k < NO_LEVER_KW)
            self._issue("no_lever", not lever, placeholders={"k": f"{self.pump.k or 0:.2f}"})
            self.ready, self.ready_missing = check.readiness(self.check, self.following, lever, self.check.get("winter"))
            self._issue_ready()
            self._issue_comfort()
            await self._async_learn_rooms(rows)
            await self._async_curve(rows)
            if extra.get("pv_k"):
                self.pv_k = extra["pv_k"]
            if extra.get("load_profile"):
                self.load_profile = extra["load_profile"]
            self.learn_info = {"at": dt_util.now().isoformat(timespec="seconds"), "house": house.reason, "scores": house.scores,
                               "heat_pump": note, "rows": len(rows), "heating_hours": sum(1 for r in rows if r.Q > 0.3),
                               "rows_with_setpoint": sum(1 for r in rows if r.sp is not None),
                               "rows_with_room_sensor": sum(1 for r in rows if r.room_sensor),
                               "rows_with_thermostat_reading": sum(1 for r in rows if r.T_th is not None),
                               "last_row": datetime.fromtimestamp(max(r.ts for r in rows), tz=timezone.utc).isoformat() if rows else None,
                               "pump_hours": sum(1 for r in rows if r.ts in self._pump_hours),
                               # heating without the thermostat asking (own heating curve?): left out of response and check
                               "unfollowed_hours": len(model.unfollowed(rows, self.house, self.pump))}
            self._issue("learning_failed", False)
            self.event("learned", house=house.reason, heat_pump=note[:300], plan_error_6h=self.check.get("rmse_6h"),
                       ready=self.ready, rows=len(rows))
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Roost learning failed")
            self._issue("learning_failed", True)
            self._notify_user("learning_failed")
            self.event("error", where="learning", error=repr(err)[:200], trace=traceback.format_exc(limit=4)[-800:])
        finally:
            self._learning = False
        await self.async_save()
        await self._async_tick(None, force_plan=True)

