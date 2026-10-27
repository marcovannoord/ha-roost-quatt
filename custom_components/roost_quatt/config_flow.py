"""Config flow by subject: heat pump and thermostat, the house, the price, solar and battery, comfort (with the\nregulation folded away), extra rooms as subentries. Likely entities are filled in (detect.py)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry, ConfigFlow, ConfigFlowResult, ConfigSubentryFlow, OptionsFlow, SubentryFlowResult,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import device_registry as dr, entity_registry as er, selector

from .const import (
    CONF_BASELINE_NIGHT, CONF_BATTERY_KW, CONF_BATTERY_KWH, CONF_BATTERY_POWER, CONF_BATTERY_RESERVE, CONF_BATTERY_SOC, CONF_BATTERY_USE,
    CONF_COMFORT, CONF_DAY_FROM, CONF_DAY_MIN, CONF_DAY_TO, CONF_EXPORT_PRICE, CONF_GRID_POWER, CONF_GRID_PREFERENCE,
    CONF_GRID_SIGN, CONF_HEAT_PUMP, CONF_HOUSE_POWER, CONF_IMPORT_ON_SETUP, CONF_IMPORT_PRICE, CONF_MAX_ABOVE,
    CONF_MIN_INTERVAL, CONF_NIGHT_MIN, CONF_PAUSE_HOURS, CONF_PV_FORECAST, CONF_PV_FORECAST_TOMORROW, CONF_PV_POWER,
    CONF_ROOM, CONF_STORE_MAX, CONF_THERMOSTAT, CONF_WEATHER, CONF_WEATHER_SOURCE, BATTERY_USES, DEFAULTS, DOMAIN, GRID_SIGNS, WEATHER_SOURCES,
    CONF_FIXED_EXPORT_PRICE, CONF_FIXED_LOW_PRICE, CONF_FIXED_PRICE, CONF_LOW_FROM, CONF_LOW_TO, CONF_LOW_WEEKEND,
    CONF_EMITTER, CONF_HAS_BATTERY, CONF_HAS_SOLAR, CONF_PRICE_MODE, CONF_SP_MIN, CONF_USE_BAG, EMITTERS, PRICE_MODES,
    CONF_EPEX_ZONE, CONF_WINDOW_SENSORS, CONF_IMPORT_MULT, CONF_IMPORT_ADD, CONF_EXPORT_FORMULA, CONF_EXPORT_MULT, CONF_EXPORT_ADD,
    CONF_NOTIFY, CONF_WEEKLY,
)
from . import check, comfort, detect, epex, quatt, schedule
from .rooms import KINDS as ROOM_KINDS

_LOGGER = logging.getLogger(__name__)


def _ent(domain, device_class=None):
    cfg = {"domain": domain}
    if device_class:
        cfg["device_class"] = device_class
    return selector.EntitySelector(selector.EntitySelectorConfig(**cfg))


def _num(lo, hi, step, unit=None):
    cfg = {"min": lo, "max": hi, "step": step, "mode": selector.NumberSelectorMode.BOX}
    if unit:
        cfg["unit_of_measurement"] = unit
    return selector.NumberSelector(selector.NumberSelectorConfig(**cfg))


LOGIN_KEYS: tuple[str, ...] = ()      # Roost for Quatt keeps no login: it reads the Quatt integration's entities


def _sel(options, key):
    return selector.SelectSelector(selector.SelectSelectorConfig(options=options, translation_key=key,
                                                                 mode=selector.SelectSelectorMode.DROPDOWN))


DEG = _num(10, 30, 0.5, "°C")


SOLAR_KEYS = [CONF_GRID_POWER, CONF_GRID_SIGN, CONF_PV_POWER, CONF_PV_FORECAST, CONF_PV_FORECAST_TOMORROW]
BATTERY_KEYS = [CONF_BATTERY_SOC, CONF_BATTERY_POWER, CONF_BATTERY_KWH, CONF_BATTERY_KW, CONF_BATTERY_RESERVE, CONF_BATTERY_USE, CONF_HOUSE_POWER]
ADVANCED = "advanced"
ADVANCED_KEYS = [CONF_SP_MIN, CONF_MAX_ABOVE, CONF_MIN_INTERVAL, CONF_PAUSE_HOURS, CONF_BASELINE_NIGHT, CONF_WEATHER_SOURCE, CONF_WEATHER]


def start_schema() -> vol.Schema:
    """First step: which heat pump and which thermostat."""
    return vol.Schema({
        vol.Required(CONF_NAME, default="Roost for Quatt"): selector.TextSelector(),
        vol.Required(CONF_HEAT_PUMP): selector.DeviceSelector(selector.DeviceSelectorConfig(integration="quatt")),
        vol.Required(CONF_THERMOSTAT): _ent("climate"),
        vol.Required(CONF_IMPORT_ON_SETUP, default=True): selector.BooleanSelector(),
    })


def house_schema(with_thermostat: bool) -> vol.Schema:
    """The house: room sensor, heat emitters, building register."""
    s: dict = {}
    if with_thermostat:
        s[vol.Required(CONF_THERMOSTAT)] = _ent("climate")
    s[vol.Optional(CONF_ROOM)] = _ent("sensor", "temperature")
    s[vol.Required(CONF_EMITTER, default=DEFAULTS[CONF_EMITTER])] = _sel(EMITTERS, "emitter")
    s[vol.Required(CONF_USE_BAG, default=DEFAULTS[CONF_USE_BAG])] = selector.BooleanSelector()
    s[vol.Optional(CONF_WINDOW_SENSORS)] = selector.EntitySelector(selector.EntitySelectorConfig(
        domain="binary_sensor", device_class=["window", "door", "opening"], multiple=True))
    return vol.Schema(s)


def price_mode_schema() -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_PRICE_MODE, default=DEFAULTS[CONF_PRICE_MODE]): _sel(PRICE_MODES, "price_mode"),
        vol.Optional(CONF_IMPORT_PRICE): _ent(["sensor", "input_number"]),
        vol.Optional(CONF_EXPORT_PRICE): _ent(["sensor", "input_number"]),
    })


def price_epex_schema(currency: str, country: str | None) -> vol.Schema:
    """Built-in day-ahead prices: the bidding zone, and what a kWh costs (and earns) = day-ahead × multiplier + amount."""
    unit = f"{currency}/kWh"
    zones = selector.SelectSelector(selector.SelectSelectorConfig(options=epex.ZONES, mode=selector.SelectSelectorMode.DROPDOWN))
    d = DEFAULTS
    return vol.Schema({
        vol.Required(CONF_EPEX_ZONE, default=epex.zone_for(country)): zones,
        vol.Required(CONF_IMPORT_MULT, default=d[CONF_IMPORT_MULT]): _num(0, 3, 0.001),
        vol.Required(CONF_IMPORT_ADD, default=d[CONF_IMPORT_ADD]): _num(-1, 1, 0.001, unit),
        vol.Required(CONF_EXPORT_FORMULA, default=d[CONF_EXPORT_FORMULA]): selector.BooleanSelector(),
        vol.Required(CONF_EXPORT_MULT, default=d[CONF_EXPORT_MULT]): _num(0, 3, 0.001),
        vol.Required(CONF_EXPORT_ADD, default=d[CONF_EXPORT_ADD]): _num(-1, 1, 0.001, unit),
    })


def price_schema(currency: str) -> vol.Schema:
    """A fixed contract: one rate, optionally a low rate at night and in the weekend, optionally a fixed export price."""
    unit = f"{currency}/kWh"
    return vol.Schema({
        vol.Required(CONF_FIXED_PRICE): _num(0, 2, 0.001, unit),
        vol.Optional(CONF_FIXED_LOW_PRICE): _num(0, 2, 0.001, unit),
        vol.Required(CONF_LOW_FROM, default=DEFAULTS[CONF_LOW_FROM]): _num(0, 23, 1, "h"),
        vol.Required(CONF_LOW_TO, default=DEFAULTS[CONF_LOW_TO]): _num(0, 23, 1, "h"),
        vol.Required(CONF_LOW_WEEKEND, default=DEFAULTS[CONF_LOW_WEEKEND]): selector.BooleanSelector(),
        vol.Optional(CONF_FIXED_EXPORT_PRICE): _num(-1, 2, 0.001, unit),
    })


def solar_schema() -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_HAS_SOLAR, default=False): selector.BooleanSelector(),
        vol.Required(CONF_HAS_BATTERY, default=False): selector.BooleanSelector(),
    })


def solar_details_schema(solar: bool, battery: bool) -> vol.Schema:
    """Only the fields for what the house has."""
    s: dict = {}
    if solar:
        s[vol.Optional(CONF_PV_POWER)] = _ent("sensor", "power")
        s[vol.Optional(CONF_PV_FORECAST)] = _ent("sensor")
        s[vol.Optional(CONF_PV_FORECAST_TOMORROW)] = _ent("sensor")
        s[vol.Optional(CONF_GRID_POWER)] = _ent("sensor", "power")
        s[vol.Required(CONF_GRID_SIGN, default=DEFAULTS[CONF_GRID_SIGN])] = _sel(GRID_SIGNS, "grid_sign")
    if battery:
        s[vol.Optional(CONF_BATTERY_SOC)] = _ent("sensor", "battery")
        s[vol.Optional(CONF_BATTERY_POWER)] = _ent("sensor", "power")
        s[vol.Optional(CONF_BATTERY_KWH)] = _num(0, 200, 0.1, "kWh")
        s[vol.Optional(CONF_BATTERY_KW)] = _num(0, 50, 0.1, "kW")
        s[vol.Optional(CONF_BATTERY_RESERVE, default=DEFAULTS[CONF_BATTERY_RESERVE])] = _num(0, 100, 1, "%")
        s[vol.Required(CONF_BATTERY_USE, default=DEFAULTS[CONF_BATTERY_USE])] = _sel(BATTERY_USES, "battery_use")
        s[vol.Optional(CONF_HOUSE_POWER)] = _ent("sensor", "power")
    s[vol.Optional(CONF_GRID_PREFERENCE, default=DEFAULTS[CONF_GRID_PREFERENCE])] = _num(0, 0.5, 0.005)
    return vol.Schema(s)


SOLAR_SECTION, BATTERY_SECTION = "solar_section", "battery_section"


def solar_options_schema(solar: bool, battery: bool) -> vol.Schema:
    """Options: one screen, a block for solar (and the grid meter) and one for the home battery, each with its tick
    and its sensors; the block of what the house has is open."""
    sol = solar_details_schema(True, False).schema
    bat = solar_details_schema(False, True).schema
    pref = next(k for k in sol if str(k) == CONF_GRID_PREFERENCE)
    return vol.Schema({
        vol.Required(SOLAR_SECTION): section(vol.Schema({vol.Required(CONF_HAS_SOLAR, default=False): selector.BooleanSelector(),
                                                         **{k: v for k, v in sol.items() if str(k) != CONF_GRID_PREFERENCE}}),
                                             {"collapsed": not solar}),
        vol.Required(BATTERY_SECTION): section(vol.Schema({vol.Required(CONF_HAS_BATTERY, default=False): selector.BooleanSelector(),
                                                           **{k: v for k, v in bat.items() if str(k) != CONF_GRID_PREFERENCE}}),
                                               {"collapsed": not battery}),
        pref: sol[pref],
    })


def comfort_schema() -> vol.Schema:
    """What everyone sets; the regulation and the weather source folded away under 'advanced'."""
    d = DEFAULTS
    advanced = vol.Schema({
        vol.Required(CONF_SP_MIN, default=d[CONF_SP_MIN]): _num(14, 25, 0.5, "°C"),
        vol.Required(CONF_MAX_ABOVE, default=d[CONF_MAX_ABOVE]): _num(0.5, 3, 0.5, "°C"),
        vol.Required(CONF_MIN_INTERVAL, default=d[CONF_MIN_INTERVAL]): _num(15, 240, 15, "min"),
        vol.Required(CONF_PAUSE_HOURS, default=d[CONF_PAUSE_HOURS]): _num(0.5, 12, 0.5, "h"),
        vol.Required(CONF_BASELINE_NIGHT, default=d[CONF_BASELINE_NIGHT]): _num(0, 30, 0.5, "°C"),
        vol.Required(CONF_WEATHER_SOURCE, default=d[CONF_WEATHER_SOURCE]): _sel(WEATHER_SOURCES, "weather_source"),
        vol.Optional(CONF_WEATHER): _ent("weather"),
    })
    return vol.Schema({
        vol.Required(CONF_DAY_FROM, default=d[CONF_DAY_FROM]): _num(0, 23, 1, "h"),
        vol.Required(CONF_DAY_TO, default=d[CONF_DAY_TO]): _num(1, 24, 1, "h"),
        vol.Required(CONF_COMFORT, default=d[CONF_COMFORT]): DEG,
        vol.Required(CONF_DAY_MIN, default=d[CONF_DAY_MIN]): DEG,
        vol.Required(CONF_NIGHT_MIN, default=d[CONF_NIGHT_MIN]): DEG,
        vol.Required(CONF_STORE_MAX, default=d[CONF_STORE_MAX]): DEG,
        vol.Optional(schedule.SECTION): section(vol.Schema({
            vol.Required("enabled", default=False): selector.BooleanSelector(),
            **{vol.Optional(day, default=""): selector.TextSelector() for day in schedule.DAYS},
        }), {"collapsed": True}),
        vol.Required(ADVANCED): section(advanced, {"collapsed": True}),
    })


def _flat(user_input: dict) -> dict:
    """A form with a section -> one level, as stored."""
    out = {k: v for k, v in user_input.items() if k not in (ADVANCED, schedule.SECTION)}
    out.update(user_input.get(ADVANCED) or {})
    if schedule.SECTION in user_input:
        weekly = user_input[schedule.SECTION] or {}
        out[schedule.ENABLED] = bool(weekly.get("enabled", False))
        raw = {day: weekly.get(day, "") for day in schedule.DAYS}
        try:
            out[schedule.WEEK] = schedule.normalise(raw)
        except ValueError:
            out[schedule.WEEK] = raw             # keep the invalid input visible for correction
    return out


def _nested(values: dict) -> dict:
    """Stored values -> suggested values for a form with the 'advanced' section."""
    legacy = [[int(values.get(CONF_DAY_FROM, DEFAULTS[CONF_DAY_FROM]))*60,
               int(values.get(CONF_DAY_TO, DEFAULTS[CONF_DAY_TO]))*60]]
    week = values.get(schedule.WEEK, {})
    weekly = {"enabled": bool(values.get(schedule.ENABLED, False))}
    for day in schedule.DAYS:
        periods = week.get(day, legacy)
        weekly[day] = periods if isinstance(periods, str) else schedule.format_day(periods)
    return {**{k: v for k, v in values.items() if k not in (*ADVANCED_KEYS, schedule.ENABLED, schedule.WEEK)},
            ADVANCED: {k: values[k] for k in ADVANCED_KEYS if k in values},
            schedule.SECTION: weekly}


def _suggest(hass: HomeAssistant, values: dict, found: dict) -> dict:
    """Detected entities fill only what is still empty."""
    return {**{k: v for k, v in found.items() if v}, **{k: v for k, v in values.items() if v not in (None, "")}}


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in (None, "")}


def _check_quatt(hass: HomeAssistant, device_id: str) -> bool:
    """The device belongs to a Quatt integration entry that has the CIC's state, heat and electricity."""
    dev = dr.async_get(hass).async_get(device_id)
    if dev is None:
        return False
    reg = er.async_get(hass)
    found = [(e.unique_id, e.entity_id) for entry_id in quatt.device_entry_ids(dev)
             for e in er.async_entries_for_config_entry(reg, entry_id) if e.platform == "quatt"]
    return quatt.is_quatt(quatt.resolve(found))


def _check_price(d: dict) -> dict[str, str]:
    return {CONF_IMPORT_PRICE: "price_needed"} if d.get(CONF_PRICE_MODE, "sensor") == "sensor" and not d.get(CONF_IMPORT_PRICE) else {}


def _check_comfort(d: dict) -> dict[str, str]:
    errors = {}
    if schedule.WEEK in d:
        try:
            schedule.normalise(d[schedule.WEEK])
        except ValueError:
            errors["base"] = "invalid_schedule"
    elif d.get(schedule.ENABLED):
        errors["base"] = "invalid_schedule"
    if float(d[CONF_COMFORT]) < float(d[CONF_DAY_MIN]):
        errors[CONF_COMFORT] = "comfort_below_min"
    if float(d[CONF_STORE_MAX]) < float(d[CONF_COMFORT]):
        errors[CONF_STORE_MAX] = "store_below_comfort"
    if float(d.get(CONF_SP_MIN, 0)) > float(d[CONF_COMFORT]):
        errors["base"] = "lowest_above_comfort"
    if int(d[CONF_DAY_TO]) <= int(d[CONF_DAY_FROM]):
        errors[CONF_DAY_TO] = "day_order"
    if d.get(CONF_WEATHER_SOURCE) == "entity" and not d.get(CONF_WEATHER):
        errors["base"] = "weather_needed"
    return errors


async def _comfort_from_history(hass: HomeAssistant, thermostat: str | None, days: int = 14) -> dict | None:
    """Comfort settings suggested from the thermostat's setpoints in the recorder (comfort.from_history)."""
    if not thermostat:
        return None
    try:
        from homeassistant.components.recorder import get_instance, history
        from homeassistant.util import dt as dt_util
        end = dt_util.utcnow()
        start = end - timedelta(days=days)
        res = await get_instance(hass).async_add_executor_job(
            partial(history.state_changes_during_period, hass, start, end, entity_id=thermostat, include_start_time_state=True))
        changes = sorted((s.last_changed.timestamp(), s.attributes.get("temperature")) for s in res.get(thermostat, []))
        samples = []
        t, i, sp = start.timestamp() + 1800, 0, None
        while t < end.timestamp():
            while i < len(changes) and changes[i][0] <= t:
                sp = changes[i][1] if changes[i][1] is not None else sp
                i += 1
            if sp is not None:
                samples.append((dt_util.as_local(datetime.fromtimestamp(t, tz=timezone.utc)).hour, float(sp)))
            t += 3600
        return comfort.from_history(samples)
    except Exception:  # noqa: BLE001 - only a suggestion: the defaults remain
        return None


def _summary(hass: HomeAssistant, o: dict, rooms: int) -> dict[str, str]:
    """What is set now, for the options menu (names and numbers only: the words come from the translation)."""
    def n(v):
        return f"{float(v):g}"
    cur = hass.config.currency or "EUR"
    if o.get(CONF_PRICE_MODE) == "fixed":
        price = f"{n(o.get(CONF_FIXED_PRICE, 0))} {cur}/kWh" + (f" / {n(o[CONF_FIXED_LOW_PRICE])}" if o.get(CONF_FIXED_LOW_PRICE) is not None else "")
    elif o.get(CONF_PRICE_MODE) == "epex":
        price = (f"EPEX {o.get(CONF_EPEX_ZONE) or epex.zone_for(hass.config.country)} × {n(o.get(CONF_IMPORT_MULT, 1))}"
                 f" + {n(o.get(CONF_IMPORT_ADD, 0))} {cur}/kWh")
    else:
        price = detect.friendly(hass, o.get(CONF_IMPORT_PRICE))
    solar = []
    if o.get(CONF_PV_POWER) or o.get(CONF_PV_FORECAST):
        solar.append(detect.friendly(hass, o.get(CONF_PV_POWER) or o.get(CONF_PV_FORECAST)))
    if o.get(CONF_BATTERY_SOC):
        solar.append(f"{n(o[CONF_BATTERY_KWH])} kWh" if o.get(CONF_BATTERY_KWH) else detect.friendly(hass, o.get(CONF_BATTERY_SOC)))
    return {
        "house": " · ".join(x for x in (detect.friendly(hass, o.get(CONF_THERMOSTAT)), detect.friendly(hass, o.get(CONF_ROOM)) if o.get(CONF_ROOM) else "") if x),
        "price": price,
        "solar": " · ".join(solar) or "—",
        "comfort": f"{_texts(hass)['weekly'] if o.get(schedule.ENABLED) else str(int(o[CONF_DAY_FROM])) + '–' + str(int(o[CONF_DAY_TO]))} · {n(o[CONF_COMFORT])} °C · min {n(o[CONF_DAY_MIN])} / {n(o[CONF_NIGHT_MIN])} °C",
        "rooms": str(rooms),
    }


def room_schema() -> vol.Schema:
    """An extra room: a sensor, its kind (the defaults for its minimum and hours) and, if wanted, other values."""
    return vol.Schema({
        vol.Required("name"): selector.TextSelector(),
        vol.Required("sensor"): _ent("sensor", "temperature"),
        vol.Required("kind", default="other"): _sel(list(ROOM_KINDS), "room_kind"),
        vol.Optional("minimum"): _num(10, 24, 0.5, "°C"),
        vol.Optional("hour_from"): _num(0, 23, 1, "h"),
        vol.Optional("hour_to"): _num(0, 24, 1, "h"),
    })


ETA_TEXT = {
    "en": {"weekly": "Weekly schedule", "ready": "now.", "lever": "not yet: the setpoint does not move the heat pump (see the repair notice).",
           "following": "not yet: the heat pump heats while the thermostat asks for no heat (is the thermostat on the Quatt CIC over OpenTherm?).",
           "import": "around {time}, after the import from the statistics and the learning that follows, if the self-check then passes.",
           "heating": "around {time}: it needs more heating hours first.",
           "heating_season": "when the heating season starts: too little heating now to check the plan.",
           "check": "maybe at the next self-check, {time}. Until it predicts well enough it learns every night.",
           "importing": "Import from the statistics: {done} of {total} months, done around {time}.",
           "basis_week": "the last week",
           "saved": "✅ Saved: {part}", "parts": {"mode": "Mode", "house": "The house", "price": "Electricity price",
                                                "solar": "Solar and home battery", "comfort": "Comfort", "notify": "Notifications"},
           "basis_winter": "the last {weeks} heating weeks of the past year, because the last week had too little heating — {passed} of {weeks} good on their own (needs {need}), and the medians below must be within the limits",
           "today": "today", "tomorrow": "tomorrow"},
    "nl": {"weekly": "Weekplanning", "ready": "nu.", "lever": "nog niet: het setpoint stuurt de warmtepomp niet (zie de reparatiemelding).",
           "following": "nog niet: de warmtepomp verwarmt terwijl de thermostaat geen warmte vraagt (zit de thermostaat via OpenTherm op de Quatt CIC?).",
           "import": "rond {time}, na de import uit de statistieken en het leren daarna, als de zelfcontrole dan slaagt.",
           "heating": "rond {time}: er zijn eerst meer stookuren nodig.",
           "heating_season": "als het stookseizoen begint: nu wordt te weinig gestookt om het plan te controleren.",
           "check": "mogelijk bij de volgende zelfcontrole, {time}. Tot hij goed genoeg voorspelt leert hij elke nacht bij.",
           "importing": "Import uit de statistieken: {done} van {total} maanden, klaar rond {time}.",
           "basis_week": "de afgelopen week",
           "saved": "✅ Opgeslagen: {part}", "parts": {"mode": "Modus", "house": "Huis en thermostaat", "price": "Stroomprijs",
                                                    "solar": "Zon en thuisaccu", "comfort": "Comfort", "notify": "Meldingen"},
           "basis_winter": "de laatste {weeks} stookweken van het afgelopen jaar, omdat de afgelopen week te weinig stookte — {passed} van {weeks} los goed (nodig: {need}), en de medianen hieronder moeten binnen de grenzen liggen",
           "today": "vandaag", "tomorrow": "morgen"},
    "de": {"weekly": "Wochenplan", "ready": "jetzt.", "lever": "noch nicht: der Sollwert bewegt die Wärmepumpe nicht (siehe die Reparaturmeldung).",
           "following": "noch nicht: die Wärmepumpe heizt, während das Thermostat keine Wärme anfordert (hängt das Thermostat per OpenTherm am Quatt CIC?).",
           "import": "gegen {time}, nach dem Import aus den Statistiken und dem Lernen danach, wenn die Selbstprüfung dann besteht.",
           "heating": "gegen {time}: es braucht erst mehr Heizstunden.",
           "heating_season": "wenn die Heizsaison beginnt: jetzt wird zu wenig geheizt, um den Plan zu prüfen.",
           "check": "vielleicht bei der nächsten Selbstprüfung, {time}. Bis es gut genug vorhersagt, lernt es jede Nacht.",
           "importing": "Import aus den Statistiken: {done} von {total} Monaten, fertig gegen {time}.",
           "basis_week": "der letzten Woche",
           "saved": "✅ Gespeichert: {part}", "parts": {"mode": "Modus", "house": "Haus und Thermostat", "price": "Strompreis",
                                                    "solar": "Solar und Heimspeicher", "comfort": "Komfort", "notify": "Benachrichtigungen"},
           "basis_winter": "den letzten {weeks} Heizwochen des vergangenen Jahres, weil die letzte Woche zu wenig geheizt hat — {passed} von {weeks} einzeln gut (nötig: {need}), und die Mediane unten müssen innerhalb der Grenzen liegen",
           "today": "heute", "tomorrow": "morgen"},
    "fr": {"weekly": "Planning hebdomadaire", "ready": "maintenant.", "lever": "pas encore : la consigne ne fait pas varier la pompe à chaleur (voir la notification de réparation).",
           "following": "pas encore : la pompe à chaleur chauffe alors que le thermostat ne demande pas de chaleur (le thermostat est-il relié au CIC Quatt en OpenTherm ?).",
           "import": "vers {time}, après l'import des statistiques et l'apprentissage qui suit, si l'auto-contrôle réussit alors.",
           "heating": "vers {time} : il faut d'abord plus d'heures de chauffe.",
           "heating_season": "au début de la saison de chauffe : trop peu de chauffe maintenant pour vérifier le plan.",
           "check": "peut-être au prochain auto-contrôle, {time}. Tant qu'il ne prévoit pas assez bien, il apprend chaque nuit.",
           "importing": "Import des statistiques : {done} sur {total} mois, terminé vers {time}.",
           "basis_week": "la dernière semaine",
           "saved": "✅ Enregistré : {part}", "parts": {"mode": "Mode", "house": "La maison et le thermostat", "price": "Prix de l'électricité",
                                                     "solar": "Solaire et batterie domestique", "comfort": "Confort", "notify": "Notifications"},
           "basis_winter": "les {weeks} dernières semaines de chauffe de l'année passée, car la dernière semaine a trop peu chauffé — {passed} sur {weeks} bonnes à elles seules (requis : {need}), et les médianes ci-dessous doivent être dans les limites",
           "today": "aujourd'hui", "tomorrow": "demain"},
}


def _texts(hass: HomeAssistant) -> dict:
    """The in-code texts in the user's language (English when Roost does not speak it)."""
    lang = (hass.config.language or "en")[:2]
    return ETA_TEXT.get(lang, ETA_TEXT["en"])


def _eta_text(hass: HomeAssistant, mgr) -> str:
    """Expected ready to steer, as a sentence in the user's language."""
    t = _texts(hass)
    if mgr is None:
        return "—"
    code, when = mgr.ready_eta()
    text = t[code] if when is None else t[code].format(time=_when(t, when))
    if mgr.importing:
        done, total, end = mgr.import_progress()
        text += "\n" + t["importing"].format(done=done, total=total, time=_when(t, end) if end else "—")
    return text


def _when(t: dict, when) -> str:
    from homeassistant.util import dt as dt_util
    today = dt_util.now().date()
    day = t["today"] if when.date() == today else t["tomorrow"] if (when.date() - today).days == 1 else when.strftime("%d-%m")
    return f"{day} {when:%H:%M}"


class RoomSubentryFlow(ConfigSubentryFlow):
    """Add or change an extra room the heat pump also heats."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        if user_input is not None:
            data = _clean(user_input)
            return self.async_create_entry(title=data["name"], data=data)
        return self.async_show_form(step_id="user", data_schema=room_schema())

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        sub = self._get_reconfigure_subentry()
        if user_input is not None:
            data = _clean(user_input)
            return self.async_update_and_abort(self._get_entry(), sub, title=data["name"], data=data)
        return self.async_show_form(step_id="reconfigure", data_schema=self.add_suggested_values_to_schema(room_schema(), dict(sub.data)))


class RoostConfigFlow(ConfigFlow, domain=DOMAIN):
    """Setup in steps by subject: heat pump and thermostat, the house, the price, solar and battery, comfort. No login:
    Roost reads the Quatt integration's entities, and the heat pump's history from Home Assistant's statistics."""

    VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {"room": RoomSubentryFlow}

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def _form(self, step_id: str, schema: vol.Schema, values: dict, errors: dict | None = None) -> ConfigFlowResult:
        return self.async_show_form(step_id=step_id, data_schema=self.add_suggested_values_to_schema(schema, values), errors=errors or {})

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not _check_quatt(self.hass, user_input[CONF_HEAT_PUMP]):
                errors[CONF_HEAT_PUMP] = "not_quatt"
            else:
                await self.async_set_unique_id(user_input[CONF_HEAT_PUMP])
                self._abort_if_unique_id_configured()
                self._data.update(_clean(user_input))
                return await self.async_step_house()
        return self._form("user", start_schema(), _suggest(self.hass, user_input or {}, {CONF_THERMOSTAT: detect.thermostat(self.hass)}), errors)

    async def async_step_house(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(_clean(user_input))
            return await self.async_step_price()
        room = detect.room_sensor(self.hass, self._data.get(CONF_THERMOSTAT), self._data.get(CONF_HEAT_PUMP))
        return self._form("house", house_schema(False), {CONF_ROOM: room} if room else {})

    async def async_step_price(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _check_price(user_input)
            if not errors:
                self._data.update(_clean(user_input))
                if user_input.get(CONF_PRICE_MODE) == "fixed":
                    return await self.async_step_price_fixed()
                if user_input.get(CONF_PRICE_MODE) == "epex":
                    return await self.async_step_price_epex()
                return await self.async_step_solar()
        imp, exp = detect.prices(self.hass)
        return self._form("price", price_mode_schema(), _suggest(self.hass, user_input or {}, {CONF_IMPORT_PRICE: imp, CONF_EXPORT_PRICE: exp}), errors)

    async def async_step_price_epex(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(_clean(user_input))
            return await self.async_step_solar()
        return self.async_show_form(step_id="price_epex", data_schema=price_epex_schema(self.hass.config.currency or "EUR", self.hass.config.country))

    async def async_step_price_fixed(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(_clean(user_input))
            return await self.async_step_solar()
        return self.async_show_form(step_id="price_fixed", data_schema=price_schema(self.hass.config.currency or "EUR"))

    async def async_step_solar(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            if user_input.get(CONF_HAS_SOLAR) or user_input.get(CONF_HAS_BATTERY):
                return await self.async_step_solar_details()
            return await self.async_step_comfort()
        found = detect.energy(self.hass)
        return self._form("solar", solar_schema(), {CONF_HAS_SOLAR: bool(found.get(CONF_PV_POWER) or found.get(CONF_PV_FORECAST)),
                                                     CONF_HAS_BATTERY: bool(found.get(CONF_BATTERY_SOC))})

    async def async_step_solar_details(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        schema = solar_details_schema(bool(self._data.get(CONF_HAS_SOLAR)), bool(self._data.get(CONF_HAS_BATTERY)))
        if user_input is not None:
            self._data.update(_clean(user_input))
            return await self.async_step_comfort()
        return self._form("solar_details", schema, detect.energy(self.hass))

    async def async_step_comfort(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            flat = _flat(user_input)
            errors = _check_comfort(flat)
            if not errors:
                data = {**self._data, **_clean(flat)}
                title = data.pop(CONF_NAME, "Roost for Quatt")
                return self.async_create_entry(title=title, data=data)
            return self._form("comfort", comfort_schema(), _nested(flat), errors)
        found = await _comfort_from_history(self.hass, self._data.get(CONF_THERMOSTAT))
        return self._form("comfort", comfort_schema(), _nested(found or {}), errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return RoostOptionsFlow()


class RoostOptionsFlow(OptionsFlow):
    """The same subjects as a menu with what is set now; each part saves when it is submitted."""

    def __init__(self) -> None:
        self._opts: dict[str, Any] | None = None
        self._saved: str | None = None

    @property
    def opts(self) -> dict[str, Any]:
        if self._opts is None:
            self._opts = {k: v for k, v in {**DEFAULTS, **self.config_entry.data, **self.config_entry.options}.items()
                          if k not in LOGIN_KEYS}
            o = self._opts
            o.setdefault(CONF_HAS_SOLAR, bool(o.get(CONF_PV_POWER) or o.get(CONF_PV_FORECAST) or o.get(CONF_GRID_POWER)))
            o.setdefault(CONF_HAS_BATTERY, bool(o.get(CONF_BATTERY_SOC)))
        return self._opts

    def _update(self, schema: vol.Schema, user_input: dict) -> None:
        for key in schema.schema:
            if str(key) == schedule.SECTION and schedule.SECTION in user_input:
                self.opts.pop(schedule.ENABLED, None)
                self.opts.pop(schedule.WEEK, None)
            if str(key) == ADVANCED:
                for k in ADVANCED_KEYS:
                    self.opts.pop(k, None)
            self.opts.pop(str(key), None)
        self.opts.update(_clean(_flat(user_input)))

    async def _async_saved(self, part: str | None = None) -> ConfigFlowResult:
        """A part was submitted: save it right away (closing the window loses nothing) and go back to the menu."""
        part = part or {"price_fixed": "price", "price_epex": "price"}.get(step := (self.cur_step or {}).get("step_id", ""), step)
        # a field left empty is gone: also from what the setup stored, which the options are laid over (#3)
        data = {k: v for k, v in self.config_entry.data.items() if k in LOGIN_KEYS or k in self.opts}
        self.hass.config_entries.async_update_entry(self.config_entry, data=data, options=dict(self.opts))
        self._saved = part
        return await self.async_step_init()

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        rooms = sum(1 for s in self.config_entry.subentries.values() if s.subentry_type == "room")
        t = _texts(self.hass)
        saved = t["saved"].format(part=t["parts"].get(self._saved, self._saved)) + "\n\n" if self._saved else ""
        return self.async_show_menu(step_id="init", menu_options=["mode", "house", "price", "solar", "comfort", "notify", "done"],
                                    description_placeholders={**_summary(self.hass, self.opts, rooms), "saved": saved})

    async def async_step_done(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_create_entry(data=dict(self.opts))

    async def async_step_mode(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Off, shadow or active, with what the self-check says: here, in Roost itself."""
        mgr = getattr(self.config_entry, "runtime_data", None)
        if user_input is not None:
            if mgr is not None:
                await mgr.async_set_mode(user_input["mode"])
            self._saved = "mode"
            return await self.async_step_init()
        c = mgr.check if mgr else {}
        ok, no = "✅", "⏳"
        missing = set(mgr.ready_missing) if mgr else {"temperature"}
        w = c.get("winter") if c.get("heating_hours", 0) < check.READY_HEATING_HOURS else None
        t = _texts(self.hass)
        if w:                       # mild weather: judged on the last heating weeks
            c = {**c, "rmse_6h": w.get("rmse_6h"), "heat_ratio": w.get("heat_ratio")}
            passed = check.winter_ok(w)
            missing = missing | ({"temperature", "heat"} if not passed else set())
        ph = {"plan_error": f"{c['rmse_6h']:.2f}" if c.get("rmse_6h") is not None else "—", "plan_ok": no if "temperature" in missing else ok,
              "hours": f"{w.get('weeks', 0)} × {check.WINTER_WEEK_HOURS}+" if w else str(c.get("heating_hours", 0)),
              "hours_ok": no if "heating_hours" in missing else ok,
              "heat": f"{c['heat_ratio']:.2f}" if c.get("heat_ratio") is not None else "—", "heat_ok": no if "heat" in missing else ok,
              "basis": t["basis_winter"].format(passed=w.get("passed", 0), weeks=w.get("weeks", 0), need=check.WINTER_PASS)
              if w else t["basis_week"],
              "follows": no if "following" in missing else ok, "lever": no if "lever" in missing else ok,
              "verdict": ok if mgr and mgr.ready else no, "eta": _eta_text(self.hass, mgr)}
        schema = vol.Schema({vol.Required("mode", default=mgr.mode if mgr else "shadow"): _sel(["off", "shadow", "active"], "mode")})
        return self.async_show_form(step_id="mode", data_schema=schema, description_placeholders=ph)

    async def async_step_house(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        schema = house_schema(True)
        if user_input is not None:
            self._update(schema, user_input)
            return await self._async_saved()
        return self.async_show_form(step_id="house", data_schema=self.add_suggested_values_to_schema(schema, self.opts))

    async def async_step_price(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        schema = price_mode_schema()
        if user_input is not None:
            errors = _check_price(user_input)
            if not errors:
                self._update(schema, user_input)
                if user_input.get(CONF_PRICE_MODE) == "fixed":
                    return await self.async_step_price_fixed()
                if user_input.get(CONF_PRICE_MODE) == "epex":
                    return await self.async_step_price_epex()
                return await self._async_saved()
        return self.async_show_form(step_id="price", data_schema=self.add_suggested_values_to_schema(schema, self.opts), errors=errors)

    async def async_step_price_epex(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        schema = price_epex_schema(self.hass.config.currency or "EUR", self.hass.config.country)
        if user_input is not None:
            self._update(schema, user_input)
            return await self._async_saved()
        return self.async_show_form(step_id="price_epex", data_schema=self.add_suggested_values_to_schema(schema, self.opts))

    async def async_step_price_fixed(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        schema = price_schema(self.hass.config.currency or "EUR")
        if user_input is not None:
            self._update(schema, user_input)
            return await self._async_saved()
        return self.async_show_form(step_id="price_fixed", data_schema=self.add_suggested_values_to_schema(schema, self.opts))

    async def async_step_solar(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        o = self.opts
        if user_input is not None:
            sol, bat = user_input.get(SOLAR_SECTION) or {}, user_input.get(BATTERY_SECTION) or {}
            for k in SOLAR_KEYS + BATTERY_KEYS + [CONF_HAS_SOLAR, CONF_HAS_BATTERY, CONF_GRID_PREFERENCE]:
                o.pop(k, None)
            o.update(_clean({k: v for k, v in sol.items() if sol.get(CONF_HAS_SOLAR) or k == CONF_HAS_SOLAR}))
            o.update(_clean({k: v for k, v in bat.items() if bat.get(CONF_HAS_BATTERY) or k == CONF_HAS_BATTERY}))
            o.update(_clean({k: v for k, v in user_input.items() if k not in (SOLAR_SECTION, BATTERY_SECTION)}))
            return await self._async_saved()
        solar, battery = bool(o.get(CONF_HAS_SOLAR)), bool(o.get(CONF_HAS_BATTERY))
        # detected sensors only for a block not set up yet: in a block already set up, a field left empty was emptied
        # on purpose and must not come back filled in (#3)
        found = {k: v for k, v in detect.energy(self.hass).items()
                 if not ((solar and k in SOLAR_KEYS) or (battery and k in BATTERY_KEYS))}
        values = _suggest(self.hass, o, found)
        suggested = {SOLAR_SECTION: {k: values[k] for k in [CONF_HAS_SOLAR] + SOLAR_KEYS if k in values},
                     BATTERY_SECTION: {k: values[k] for k in [CONF_HAS_BATTERY] + BATTERY_KEYS if k in values},
                     **({CONF_GRID_PREFERENCE: values[CONF_GRID_PREFERENCE]} if CONF_GRID_PREFERENCE in values else {})}
        return self.async_show_form(step_id="solar", data_schema=self.add_suggested_values_to_schema(
            solar_options_schema(solar, battery), suggested))

    async def async_step_notify(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Notifications: off until the user picks where they go (a notify entity, or a notify service such as
        notify.mobile_app_phone); the weekly summary on top of that."""
        schema = vol.Schema({vol.Optional(CONF_NOTIFY, default=""): selector.TextSelector(),
                             vol.Required(CONF_WEEKLY, default=False): selector.BooleanSelector()})
        if user_input is not None:
            self.opts[CONF_NOTIFY] = str(user_input.get(CONF_NOTIFY) or "").strip()
            self.opts[CONF_WEEKLY] = bool(user_input.get(CONF_WEEKLY))
            return await self._async_saved()
        return self.async_show_form(step_id="notify", data_schema=self.add_suggested_values_to_schema(
            schema, {CONF_NOTIFY: self.opts.get(CONF_NOTIFY, ""), CONF_WEEKLY: bool(self.opts.get(CONF_WEEKLY))}))

    async def async_step_comfort(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        schema = comfort_schema()
        if user_input is not None:
            errors = _check_comfort(_flat(user_input))
            if not errors:
                self._update(schema, user_input)
                return await self._async_saved()
        return self.async_show_form(step_id="comfort", data_schema=self.add_suggested_values_to_schema(schema, _nested(self.opts)), errors=errors)
