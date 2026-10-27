"""Prices per hour: a price sensor, the built-in day-ahead prices or a fixed contract, and the value of energy. A mixin of RoostManager (manager.py): the methods use its state."""
from __future__ import annotations

from .mgr_common import *  # noqa: F401,F403 - the shared imports and constants
from .mgr_common import _LOGGER, _f, _i, _iso_ts  # noqa: F401


class PricesMixin:
    def _price_seen_recent(self) -> dict[str, dict[str, float]]:
        cut = time.time() - 3 * 86400
        self.price_seen = {e: {k: v for k, v in d.items() if k >= cut} for e, d in self.price_seen.items()}
        return {e: {str(k): round(v, 5) for k, v in sorted(d.items())} for e, d in self.price_seen.items()}

    async def _async_seed_prices(self) -> None:
        """Hourly prices of the last two days from the recorder (the state of the price sensor), so hours without a
        forecast yet can be filled with the same hour a day earlier right after setup or a restart."""
        now = dt_util.utcnow()
        start = now - timedelta(hours=49)
        for key in (CONF_IMPORT_PRICE, CONF_EXPORT_PRICE):
            eid = self.conf.get(key) if self.conf.get(CONF_PRICE_MODE, "sensor") == "sensor" else None
            st = self._state(eid)
            if not eid or st is None:
                continue
            try:
                res = await get_instance(self.hass).async_add_executor_job(
                    partial(rh.state_changes_during_period, self.hass, start, now, entity_id=eid, no_attributes=True,
                            include_start_time_state=True))
            except Exception as err:  # noqa: BLE001 - without the recorder the last known price is used, as before
                _LOGGER.debug("Roost could not read the price history of %s: %s", eid, err)
                continue
            changes = [(s.last_changed.timestamp(), v) for s in res.get(eid, []) if (v := _f(s.state)) is not None]
            if not changes:
                continue
            scale = series.price_scale(st.attributes.get(ATTR_UNIT_OF_MEASUREMENT), [v for _, v in changes])
            h0 = int(start.timestamp() // 3600 * 3600) + 3600
            n = int((now.timestamp() - h0) // 3600)                # complete hours only
            seen = self.price_seen.setdefault(eid, {})
            for h, v in enumerate(series.hourly(series.slots_from_changes(changes, now.timestamp()), h0, n, fill_last=False)):
                if v is not None:
                    seen.setdefault(h0 + h * 3600, v * scale)

    def _filled(self, key: str, raw: list[float | None], now: datetime, cur: float | None) -> list[float]:
        """Hours past the forecast (tomorrow's prices come in the afternoon) from the same hour a day earlier."""
        seen = self.price_seen.setdefault(key, {})
        base = int(now.timestamp() // 3600 * 3600)
        for h, v in enumerate(raw):
            if v is not None and h > 0:                     # hour 0 is only the rest of the hour: keep the full one
                seen[base + h * 3600] = v
            elif v is not None:
                seen.setdefault(base, v)
        vals, guess = series.fill_gaps(raw, now.timestamp(), seen, cur)
        self._price_guess[key] = guess
        return [v or 0.0 for v in vals]

    def _epex_series(self, now: datetime, hours: int, mult_key: str, add_key: str, key: str) -> list[float] | None:
        """The built-in day-ahead prices through the user's formula (day-ahead × multiplier + fixed amount)."""
        if not self._epex:
            return None
        mult, add = _f(self.conf.get(mult_key)) or 0.0, _f(self.conf.get(add_key)) or 0.0
        raw = [None if v is None else epex.formula(v, mult, add) for v in series.hourly(self._epex, now.timestamp(), hours, fill_last=False)]
        cur = series.current_value(self._epex, now.timestamp())
        return self._filled(key, raw, now, epex.formula(cur, mult, add) if cur is not None else None)

    async def _async_epex(self, now: datetime) -> None:
        """Fetch the built-in day-ahead prices when due (Energy-Charts limits how often an address may ask)."""
        loc = dt_util.as_local(now)
        tomorrow_end = (dt_util.start_of_local_day(loc) + timedelta(days=2)).timestamp()
        if not epex.needs_refresh(self._epex, self._epex_at, now.timestamp(), loc.hour, tomorrow_end):
            return
        self._epex_at = now.timestamp()
        zone = self.conf.get(CONF_EPEX_ZONE) or epex.zone_for(self.hass.config.country)
        try:
            slots = await epex.async_fetch(async_get_clientsession(self.hass), zone, loc.date())
        except Exception as err:  # noqa: BLE001 - keep what there is, try again later
            self.sources["epex"] = f"error: {err}"[:120]
            self.event("epex", zone=zone, error=str(err)[:200])
            return
        if slots:
            self._epex = slots
            self.sources["epex"] = "ok"
            self.event("epex", zone=zone, slots=len(slots), until=datetime.fromtimestamp(slots[-1][1], tz=timezone.utc).isoformat())

    def _price_series(self, eid: str | None, now: datetime, hours: int) -> list[float] | None:
        st = self._state(eid)
        if st is None:
            return None
        mid = dt_util.start_of_local_day(dt_util.as_local(now)).timestamp()
        slots = series.find_slots(dict(st.attributes), mid)
        cur = _f(st.state)
        unit = st.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        scale = series.price_scale(unit, [cur] if cur is not None else [v for _, _, v in slots])     # for the state
        if slots:
            fscale = series.slot_scale(slots, unit, cur * scale if cur is not None else None, now.timestamp())
            raw = [None if v is None else v * fscale for v in series.hourly(slots, now.timestamp(), hours, fill_last=False)]
            return self._filled(eid, raw, now, cur * scale if cur is not None else None)
        self._price_guess[eid] = [h > 0 for h in range(hours)]
        return [cur * scale] * hours if cur is not None else None

    def _pv_forecast(self, start: float, hours: int) -> list[float] | None:
        slots = []
        for key in (CONF_PV_FORECAST, CONF_PV_FORECAST_TOMORROW):
            st = self._state(self.conf.get(key))
            if st is not None:
                slots += series.find_slots(dict(st.attributes))
        if slots:
            return series.energy_per_hour(sorted(slots), start, hours)
        if self.conf.get(CONF_PV_POWER) and self.pv_k:
            base = start - start % 3600
            return [self.pv_k * (self._weather.get(int(base + i * 3600)) or (0, 0, 0))[1] for i in range(hours)]
        return None

    def _fixed_series(self, now: datetime, hours: int, key: str) -> list[float] | None:
        """A fixed contract per hour ahead (normal / low rate), or the fixed export price."""
        c = self.conf
        base = int(now.timestamp() // 3600 * 3600)
        loc = [dt_util.as_local(datetime.fromtimestamp(base + i * 3600, tz=timezone.utc)) for i in range(hours)]
        if key == CONF_FIXED_EXPORT_PRICE:
            v = _f(c.get(CONF_FIXED_EXPORT_PRICE))
            return None if v is None else [v] * hours
        normal = _f(c.get(CONF_FIXED_PRICE))
        if normal is None:
            return None
        return value.fixed_prices([(x.weekday(), x.hour) for x in loc], normal, _f(c.get(CONF_FIXED_LOW_PRICE)),
                                  int(c.get(CONF_LOW_FROM, 23)), int(c.get(CONF_LOW_TO, 7)), bool(c.get(CONF_LOW_WEEKEND, True)))

    def _energy(self, now: datetime, hours: int) -> tuple[value.EnergyInputs, value.EnergyValue] | None:
        c = self.conf
        if c.get(CONF_PRICE_MODE) == "fixed":
            imp = self._fixed_series(now, hours, CONF_FIXED_PRICE)
            exp = self._fixed_series(now, hours, CONF_FIXED_EXPORT_PRICE)
            self._price_guess[CONF_FIXED_PRICE] = [False] * hours
            if imp is None:
                self.sources["price"] = "missing"
                return None
            self.sources["price"] = "fixed"
        elif c.get(CONF_PRICE_MODE) == "epex":
            imp = self._epex_series(now, hours, CONF_IMPORT_MULT, CONF_IMPORT_ADD, "epex_import")
            if imp is None:
                self.sources["price"] = "missing"
                return None
            self.sources["price"] = "epex"
            exp = self._epex_series(now, hours, CONF_EXPORT_MULT, CONF_EXPORT_ADD, "epex_export") if c.get(CONF_EXPORT_FORMULA) else None
        else:
            imp = self._price_series(c.get(CONF_IMPORT_PRICE), now, hours)
            if imp is None:
                self.sources["price"] = "missing"
                return None
            self.sources["price"] = "ok"
            exp = self._price_series(c.get(CONF_EXPORT_PRICE), now, hours) if c.get(CONF_EXPORT_PRICE) else None
        surplus = value.solar_export_now(self._kw(c.get(CONF_GRID_POWER)), self._kw(c.get(CONF_BATTERY_POWER)),
                                         self._kw(c.get(CONF_PV_POWER)), c.get(CONF_GRID_SIGN, "import_positive") == "import_positive")
        soc = self._num(c.get(CONF_BATTERY_SOC))
        load = None
        if self.load_profile and len(self.load_profile) == 24:
            h0 = dt_util.as_local(now).hour
            load = [self.load_profile[(h0 + i) % 24] for i in range(hours)]
        bat = self.battery
        grid_charge = grid_charge_to = soc_usual = None
        if bat.charges_from_grid:               # learned: the battery is also charged from the grid, in these hours
            h0 = dt_util.as_local(now).hour
            grid_charge_to = [bat.top_soc.get(str((h0 + i) % 24), 100.0) if (h0 + i) % 24 in bat.grid_hours else None
                              for i in range(hours)]
            if (self._kw(c.get(CONF_BATTERY_POWER)) or 0.0) > 0.3:
                grid_charge_to[0] = None        # discharging right now: not charging this hour after all
            if len(bat.soc_by_hour) == 24:      # its steering decides when it discharges: follow its usual charge
                soc_usual = [bat.soc_by_hour[str((h0 + i + 1) % 24)] for i in range(hours)]
            if c.get(CONF_BATTERY_USE) == "cheaper":       # the heat pump may count on its cheap charging hours
                grid_charge = [(h0 + i) % 24 in bat.charge_hours for i in range(hours)]
        holds = None
        if bat.hold_hours:                      # learned: hours in which its steering keeps the charge for later
            h0 = dt_util.as_local(now).hour
            holds = [(h0 + i) % 24 in bat.hold_hours for i in range(hours)]
            if (self._kw(c.get(CONF_BATTERY_POWER)) or 0.0) >= battery.SUPPLY_KW:
                holds[0] = False                # delivering right now after all
        inp = value.EnergyInputs(import_price=imp, export_price=exp, pv_kwh=self._pv_forecast(now.timestamp(), hours), load_kwh=load,
                                 surplus_now_kw=surplus, battery_soc=soc,
                                 battery_kwh=_f(c.get(CONF_BATTERY_KWH)) if soc is not None else None,
                                 # the charge it was seen to stop at, else the setting
                                 battery_reserve=bat.reserve if bat.reserve is not None else _f(c.get(CONF_BATTERY_RESERVE)) or 10.0,
                                 battery_max_kw=_f(c.get(CONF_BATTERY_KW)) or 5.0,
                                 grid_preference=_f(c.get(CONF_GRID_PREFERENCE)) or 0.0, grid_charge=grid_charge,
                                 grid_charge_to=grid_charge_to, soc_usual=soc_usual, battery_holds=holds)
        return inp, value.compute(inp)
