"""Constants for Roost for Quatt."""
from __future__ import annotations

DOMAIN = "roost_quatt"
STORAGE_VERSION = 1
CARD_URL = "/roost_quatt/roost-quatt-card.js"

# setup
CONF_HEAT_PUMP = "heat_pump"            # device id of the Quatt CIC (any device of the Quatt integration entry)
CONF_THERMOSTAT = "thermostat"
CONF_ROOM = "room_temperature"
CONF_IMPORT_PRICE = "import_price"
CONF_EXPORT_PRICE = "export_price"
CONF_GRID_POWER = "grid_power"
CONF_GRID_SIGN = "grid_sign"            # import_positive | export_positive
CONF_PV_POWER = "pv_power"
CONF_PV_FORECAST = "pv_forecast"
CONF_PV_FORECAST_TOMORROW = "pv_forecast_tomorrow"
CONF_BATTERY_SOC = "battery_soc"
CONF_BATTERY_POWER = "battery_power"    # + = discharging
CONF_BATTERY_KWH = "battery_kwh"
CONF_BATTERY_KW = "battery_kw"
CONF_BATTERY_RESERVE = "battery_reserve"
CONF_BATTERY_USE = "battery_use"        # house | cheaper: may the heat pump count on the battery's cheap grid charging
CONF_HOUSE_POWER = "house_power"
CONF_WEATHER_SOURCE = "weather_source"  # open_meteo | entity
CONF_WEATHER = "weather_entity"
CONF_IMPORT_ON_SETUP = "import_history"
CONF_HAS_SOLAR = "has_solar"            # setup: show the solar fields
CONF_HAS_BATTERY = "has_battery"        # setup: show the home battery fields
CONF_EMITTER = "emitter"                # floor | radiators | both: starting values and wording
CONF_WINDOW_SENSORS = "window_sensors"  # optional: window/door sensors (a window open: Roost waits, does not learn from it)
CONF_USE_BAG = "use_bag"                # opt-in: building data from the Dutch register (PDOK)
CONF_PRICE_MODE = "price_mode"          # sensor (dynamic, with a forecast) | epex (built in) | fixed (a contract)
CONF_EPEX_ZONE = "epex_zone"            # bidding zone for the built-in day-ahead prices
CONF_IMPORT_MULT = "import_mult"        # built-in prices: what a kWh costs = day-ahead × multiplier + fixed amount
CONF_IMPORT_ADD = "import_add"
CONF_EXPORT_FORMULA = "export_formula"  # export by its own formula (off: net metering, export worth the import price)
CONF_EXPORT_MULT = "export_mult"
CONF_EXPORT_ADD = "export_add"
CONF_FIXED_PRICE = "fixed_price"        # per kWh, all in
CONF_FIXED_LOW_PRICE = "fixed_low_price"  # optional: the low (night/weekend) rate
CONF_LOW_FROM = "low_from"
CONF_LOW_TO = "low_to"
CONF_LOW_WEEKEND = "low_weekend"
CONF_FIXED_EXPORT_PRICE = "fixed_export_price"  # optional: empty = net metering (export worth the import price)

# comfort and control (options)
CONF_DAY_FROM = "day_from"
CONF_DAY_TO = "day_to"
CONF_COMFORT = "comfort"
CONF_WEEKLY_COMFORT = "weekly_comfort"
CONF_COMFORT_SCHEDULE = "comfort_schedule"
CONF_DAY_MIN = "day_min"
CONF_NIGHT_MIN = "night_min"
CONF_STORE_MAX = "store_max"
CONF_SP_MIN = "lowest_setpoint"        # Roost never sets the thermostat lower (also what stays if HA is down)
CONF_MAX_ABOVE = "max_above_room"
CONF_MIN_INTERVAL = "min_interval"
CONF_PAUSE_HOURS = "pause_hours"
CONF_NOTIFY = "notify_target"           # optional: where Roost sends a notification (off when empty)
CONF_WEEKLY = "weekly_report"           # a summary every Monday morning (needs CONF_NOTIFY)
AWAY_MIN = 16.0                         # the default minimum while away
CONF_BASELINE_NIGHT = "baseline_night"  # 0 = no night setback in the comparison
CONF_GRID_PREFERENCE = "grid_preference"

DEFAULTS = {
    CONF_WEEKLY_COMFORT: False,
    CONF_DAY_FROM: 7, CONF_DAY_TO: 22, CONF_COMFORT: 20.5, CONF_DAY_MIN: 20.0, CONF_NIGHT_MIN: 19.0, CONF_STORE_MAX: 22.5, CONF_SP_MIN: 19.0,
    CONF_MAX_ABOVE: 1.0, CONF_MIN_INTERVAL: 60, CONF_PAUSE_HOURS: 2, CONF_BASELINE_NIGHT: 0, CONF_GRID_PREFERENCE: 0.0,
    CONF_GRID_SIGN: "import_positive", CONF_WEATHER_SOURCE: "open_meteo", CONF_BATTERY_RESERVE: 10, CONF_BATTERY_USE: "house", CONF_IMPORT_ON_SETUP: True,
    CONF_PRICE_MODE: "sensor", CONF_IMPORT_MULT: 1.21, CONF_IMPORT_ADD: 0.0, CONF_EXPORT_FORMULA: False,
    CONF_EXPORT_MULT: 1.0, CONF_EXPORT_ADD: 0.0, CONF_USE_BAG: False, CONF_EMITTER: "floor", CONF_LOW_FROM: 23, CONF_LOW_TO: 7, CONF_LOW_WEEKEND: True,
}
PRICE_MODES = ["sensor", "epex", "fixed"]
EMITTERS = ["floor", "radiators", "both"]
MODES = ["off", "shadow", "active"]
GRID_SIGNS = ["import_positive", "export_positive"]
BATTERY_USES = ["house", "cheaper"]
WEATHER_SOURCES = ["open_meteo", "entity"]

# the Quatt integration's entities by role: quatt.QUATT

TICK_SECONDS = 120
PLAN_MINUTES = 15
WEATHER_MINUTES = 30
LEARN_HOUR, LEARN_MINUTE = 3, 30
HISTORY_DAYS_FIRST = 365      # first learning run: everything up to this
HISTORY_DAYS = 365            # never more than a year: a house changes (insulation), recent heating counts most
IMPORT_DAYS = 365             # history read from Home Assistant's long-term statistics
