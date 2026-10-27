"""Looking after the user and the thermostat: notifications (only when the user chose where), a thermostat that cannot be
reached or set, the thermostat back to comfort when Roost stops steering, away, comfort from the card, the weekly
summary and where the heat pump's electricity came from (own solar, the home battery, the grid). A mixin of
RoostManager (manager.py): the methods use its state."""
from __future__ import annotations

from .mgr_common import *  # noqa: F401,F403 - the shared imports and constants
from .mgr_common import _LOGGER, _f  # noqa: F401
from .const import AWAY_MIN, CONF_HOUSE_POWER, CONF_NOTIFY, CONF_SP_MIN, CONF_WEEKLY
from . import comfort, value
from .value import source_split  # noqa: F401 - where the heat pump's power comes from

THERMOSTAT_GONE_MIN = 15        # the thermostat unavailable this long: a notice (and Roost leaves it alone meanwhile)
SET_FAILS = 3                   # this many failed changes in a row: a notice
NOTIFY_AGAIN_H = 12             # the same notification at most this often

# Notifications in the user's language (Home Assistant's language; English when not one of these)
TEXTS = {
    "en": {"title": "Roost",
           "thermostat_unavailable": "The thermostat cannot be reached. Roost leaves it alone until it is back.",
           "set_failed": "Roost could not change the thermostat {n} times in a row: {error}",
           "steering_not_ready": "Roost steers with the model it had: the check of the house model did not pass. Look at it in the card.",
           "learning_failed": "Learning the house failed tonight; Roost goes on with the model it had.",
           "weekly": "Last week: heating {kwh} kWh, cost {cost}, saving {saving} against a steady thermostat. {below} min below comfort, {hand} changes by hand.{sources}",
           "sources": " Heating electricity: {sun} % own solar, {bat} % battery, {grid} % grid."},
    "nl": {"title": "Roost",
           "thermostat_unavailable": "De thermostaat is niet bereikbaar. Roost laat hem met rust tot hij terug is.",
           "set_failed": "Roost kon de thermostaat {n} keer achter elkaar niet wijzigen: {error}",
           "steering_not_ready": "Roost stuurt met het model dat het had: de controle van het huismodel is niet geslaagd. Kijk in de kaart.",
           "learning_failed": "Het huis leren is vannacht mislukt; Roost gaat door met het model dat het had.",
           "weekly": "Afgelopen week: {kwh} kWh stroom voor verwarming, kosten {cost}, besparing {saving} tegenover een vaste thermostaat. {below} min onder comfort, {hand} wijzigingen met de hand.{sources}",
           "sources": " Stroom voor verwarming: {sun} % eigen zon, {bat} % accu, {grid} % net."},
    "de": {"title": "Roost",
           "thermostat_unavailable": "Das Thermostat ist nicht erreichbar. Roost lässt es in Ruhe, bis es zurück ist.",
           "set_failed": "Roost konnte das Thermostat {n}-mal nacheinander nicht ändern: {error}",
           "steering_not_ready": "Roost steuert mit dem bisherigen Modell: die Prüfung des Hausmodells ist nicht bestanden. Schau in die Karte.",
           "learning_failed": "Das Lernen des Hauses ist heute Nacht fehlgeschlagen; Roost macht mit dem bisherigen Modell weiter.",
           "weekly": "Letzte Woche: {kwh} kWh Heizstrom, Kosten {cost}, Ersparnis {saving} gegenüber einem festen Thermostat. {below} min unter Komfort, {hand} Änderungen von Hand.{sources}",
           "sources": " Heizstrom: {sun} % eigene Sonne, {bat} % Akku, {grid} % Netz."},
    "fr": {"title": "Roost",
           "thermostat_unavailable": "Le thermostat est injoignable. Roost le laisse tranquille jusqu'à son retour.",
           "set_failed": "Roost n'a pas pu changer le thermostat {n} fois de suite : {error}",
           "steering_not_ready": "Roost pilote avec le modèle qu'il avait : la vérification du modèle de la maison n'a pas réussi. Voir la carte.",
           "learning_failed": "L'apprentissage de la maison a échoué cette nuit ; Roost continue avec le modèle qu'il avait.",
           "weekly": "Semaine dernière : {kwh} kWh de chauffage, coût {cost}, économie {saving} par rapport à un thermostat fixe. {below} min sous le confort, {hand} changements à la main.{sources}",
           "sources": " Électricité de chauffage : {sun} % solaire, {bat} % batterie, {grid} % réseau."},
}


class CareMixin:
    def _care_init(self) -> None:
        self._notified: dict[str, float] = {}       # kind -> when last sent
        self._th_gone_since: float | None = None
        self._set_fails = 0
        self._src_acc = [0.0, 0.0, 0.0]             # kWh of the heat pump this hour from solar, battery, grid

    # ------------------------------------------------------------ notifications (the user turns them on)
    def _texts(self) -> dict:
        return TEXTS.get((self.hass.config.language or "en")[:2], TEXTS["en"])

    def _notify_user(self, kind: str, force: bool = False, **fmt) -> None:
        target = str(self.conf.get(CONF_NOTIFY) or "").strip()
        if not target:
            return
        now = time.time()
        if not force and now - self._notified.get(kind, 0.0) < NOTIFY_AGAIN_H * 3600:
            return
        self._notified[kind] = now
        t = self._texts()
        msg = t[kind].format(**fmt)
        self.spawn(self._async_send(target, t["title"], msg), f"notify {kind}")

    async def _async_send(self, target: str, title: str, message: str) -> None:
        try:
            if target.startswith("notify.") and self.hass.states.get(target) is not None:     # a notify entity
                await self.hass.services.async_call("notify", "send_message", {ATTR_ENTITY_ID: target, "title": title,
                                                                                "message": message}, blocking=True)
            else:                                                                           # a notify service
                name = target.removeprefix("notify.")
                await self.hass.services.async_call("notify", name, {"title": title, "message": message}, blocking=True)
            self.event("notified", target=target)
        except Exception as err:  # noqa: BLE001 - a notification never gets in the way
            _LOGGER.warning("Roost could not send a notification to %s: %s", target, err)
            self.event("notify_failed", target=target, error=str(err)[:200])

    # ------------------------------------------------------------ the thermostat
    def thermostat_reachable(self) -> bool:
        st = self.hass.states.get(self.conf[CONF_THERMOSTAT])
        return st is not None and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)

    def _watch_thermostat(self, t: float) -> None:
        """Unavailable for a while: a notice (and a notification when chosen); back: the notice goes."""
        if self.thermostat_reachable():
            back = self._th_gone_since is not None
            self._th_gone_since = None                  # first: the planning below runs this check again
            self._issue("thermostat_unavailable", False)
            if back:
                self.event("thermostat_back")
                # plan again with what the thermostat really has (a plan made without it would be followed meanwhile)
                self.hass.async_create_background_task(self._async_tick(None, force_plan=True), "roost: plan after the thermostat is back")
            return
        if self._th_gone_since is None:
            self._th_gone_since = t
            self.event("thermostat_gone")
        if t - self._th_gone_since >= THERMOSTAT_GONE_MIN * 60 and self.mode == "active":
            if "thermostat_unavailable" not in self.health.issues:
                self._notify_user("thermostat_unavailable")
            self._issue("thermostat_unavailable", True)

    def _set_result(self, ok: bool, error: str = "") -> None:
        if ok:
            self._set_fails = 0
            self._issue("set_failed", False)
            return
        self._set_fails += 1
        if self._set_fails >= SET_FAILS:
            if "set_failed" not in self.health.issues:
                self._notify_user("set_failed", n=self._set_fails, error=error[:120])
            self._issue("set_failed", True, placeholders={"error": error[:120]})

    async def _async_back_to_comfort(self, why: str) -> None:
        """Roost stops steering (off, shadow, removed): the thermostat back on the comfort temperature, not left at
        whatever the plan had (a low setting in an expensive hour)."""
        target = float(self.conf[CONF_COMFORT])
        if not self.thermostat_reachable() or self.thermostat_sp() == target:
            return
        ctx = Context()
        self._contexts[ctx.id] = time.time()
        try:
            await self.hass.services.async_call("climate", "set_temperature",
                                                {ATTR_ENTITY_ID: self.conf[CONF_THERMOSTAT], "temperature": self._c_to_sys(target)},
                                                blocking=True, context=ctx)
            self.event("back_to_comfort", why=why, new=target)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Roost could not set the thermostat back to comfort: %s", err)

    # ------------------------------------------------------------ away, comfort from the card
    def is_away(self, ts: float | None = None) -> bool:
        u = self.mem.away_until
        return bool(u and (ts if ts is not None else time.time()) < u)

    async def async_away(self, until: float, minimum: float | None) -> None:
        self.mem.away_until = until
        self.mem.away_min = float(minimum) if minimum is not None else AWAY_MIN
        self.event("away", until=datetime.fromtimestamp(until, tz=timezone.utc).isoformat(timespec="minutes"),
                   minimum=self.mem.away_min)
        await self.async_save()
        await self._async_tick(None, force_plan=True)

    async def async_home(self) -> None:
        if self.mem.away_until:
            self.event("home")
        self.mem.away_until = None
        await self.async_save()
        await self._async_tick(None, force_plan=True)

    async def async_set_settings(self, **changes) -> None:
        """Temperatures and comfort hours from the card: Roost's own settings (not the thermostat), without a reload.
        The setting that was changed wins: the others follow it (comfort never below the day minimum, storing never
        below comfort, the lowest setpoint never above comfort); comfort hours must end after they start."""
        keys = {"comfort": CONF_COMFORT, "day_min": CONF_DAY_MIN, "night_min": CONF_NIGHT_MIN, "store_max": CONF_STORE_MAX,
                "lowest_setpoint": CONF_SP_MIN, "day_from": CONF_DAY_FROM, "day_to": CONF_DAY_TO}
        c = {k: self.conf.get(v) for k, v in keys.items()}
        new = {k: v for k, v in changes.items() if k in keys and v is not None}
        for k, v in new.items():
            c[k] = int(v) if k in ("day_from", "day_to") else round(float(v) * 2) / 2
        f = comfort.adjust_settings(c, set(new))
        if f is None:
            from homeassistant.exceptions import ServiceValidationError
            raise ServiceValidationError("The comfort hours must end after they start")
        opts = {**self.entry.options, **{keys[k]: v for k, v in f.items()}}
        from . import _conf_key
        # settings Roost takes as they are: no reload for them. Known before saving: the update listener may run
        # within async_update_entry (an eager task), and then saw the old key and reloaded Roost (card unavailable)
        self.conf_key = _conf_key(self.entry, opts)
        self.hass.config_entries.async_update_entry(self.entry, options=opts)
        self.event("settings", **{k: f[k] for k in new})
        await self._async_tick(None, force_plan=True)

    # ------------------------------------------------------------ where the heat pump's electricity came from
    def _sources_tick(self, dt: float) -> None:
        c = self.conf
        if not (c.get(CONF_PV_POWER) or c.get(CONF_BATTERY_POWER)):
            return
        if self.pump_state() != "heating":
            return                  # hot water (and defrost of it) is not heating: only space heating is counted
        hp = self._kw(self.ent.get("power_in"))
        grid = self._kw(c.get(CONF_GRID_POWER))
        if hp is None or grid is None or hp <= 0:
            return
        pv = self._kw(c.get(CONF_PV_POWER)) or 0.0
        bat = self._kw(c.get(CONF_BATTERY_POWER)) or 0.0
        house = self._kw(c.get(CONF_HOUSE_POWER))
        if house is None:
            house = value.house_use(grid, pv, bat, c.get(CONF_GRID_SIGN, "import_positive") == "import_positive")
        for i, kw in enumerate(value.source_split(hp, house, pv, bat)):
            self._src_acc[i] += kw * dt / 3600

    def _sources_close(self, entry: dict) -> None:
        if sum(self._src_acc) > 0:
            entry["e_sun"], entry["e_bat"], entry["e_grid"] = (round(x, 3) for x in self._src_acc)

    def _sources_reset(self) -> None:
        self._src_acc = [0.0, 0.0, 0.0]

    # ------------------------------------------------------------ the weekly summary (Monday morning, when chosen)
    async def _async_weekly(self, _now: datetime) -> None:
        if not self.conf.get(CONF_WEEKLY) or dt_util.now().weekday() != 0:
            return
        today = dt_util.now().date()
        days = [(today - timedelta(days=i)).isoformat() for i in range(1, 8)]
        ds = [self.day_stats[d] for d in days if d in self.day_stats]
        if not ds:
            return
        cur = self.hass.config.currency or "EUR"
        money = lambda v: f"{v:.2f} {cur}" if v is not None else "—"      # noqa: E731
        hrs = [e for e in self.hour_log if dt_util.as_local(datetime.fromtimestamp(e["ts"], tz=timezone.utc)).date().isoformat() in days]
        sun, bat, grid = (sum(e.get(k, 0.0) for e in hrs) for k in ("e_sun", "e_bat", "e_grid"))
        total = sun + bat + grid
        t = self._texts()
        sources = t["sources"].format(sun=round(100 * sun / total), bat=round(100 * bat / total), grid=round(100 * grid / total)) if total > 0.5 else ""
        self._notify_user("weekly", force=True, kwh=round(sum(d.get("kwh") or 0.0 for d in ds), 1),
                          cost=money(sum(d.get("cost") or 0.0 for d in ds)),
                          saving=money(sum(d.get("saving") or 0.0 for d in ds) if any(d.get("saving") is not None for d in ds) else None),
                          below=round(sum(d.get("below_min") or 0 for d in ds)), hand=sum(d.get("by_hand") or 0 for d in ds),
                          sources=sources)
