"""Sensors: the planned setpoint (with the 24-hour plan for the card), cost and saving, the learned models."""
from __future__ import annotations

import time
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import RoostConfigEntry, planner, schedule
from .const import CONF_DAY_FROM, CONF_DAY_TO, CONF_EMITTER, CONF_THERMOSTAT
from .entity import RoostEntity


async def async_setup_entry(hass: HomeAssistant, entry: RoostConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    m = entry.runtime_data
    async_add_entities([SetpointSensor(m), SavingNext24hSensor(m), SavingYesterdaySensor(m), SavingMonthSensor(m),
                        CostTodaySensor(m), EnergyTodaySensor(m), EnergyValueSensor(m), HouseModelSensor(m), HeatPumpModelSensor(m),
                        ImportSensor(m), ImportProgressSensor(m), PlanAccuracySensor(m), RoomExpectedSensor(m), HeatPlannedSensor(m),
                        HeatingCurveSensor(m)])


def _cur(hass) -> str:
    return hass.config.currency or "EUR"


class SetpointSensor(RoostEntity, SensorEntity):
    """The setpoint Roost wants now; the attributes carry the plan the dashboard card draws."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:home-thermometer"
    _unrecorded_attributes = frozenset({"plan", "start", "comfort", "day_min", "night_min", "store_max", "day_hours", "rooms",
                                         "pump_runs", "room_recent", "comfort_week", "own_kw", "comfort_masks", "comfort_schedule",
                                         "plan_why", "thermostat_entity", "lowest_setpoint",
                                         "day_from", "day_to", "max_above_room", "gas_boiler_hours", "hybrid"})

    def __init__(self, mgr) -> None:
        super().__init__(mgr, "setpoint")

    @property
    def native_value(self):
        return self.mgr.planned_sp(time.time())

    @property
    def extra_state_attributes(self):
        m = self.mgr
        p, d = m.plan, m.decision
        s = m.settings()
        # English text for automations and logs; code + args so the card can show it in the user's language
        attrs = {"mode": m.mode, "reason": str(m.reason), "reason_code": m.reason.code, "reason_args": m.reason.args,
                 "decision": d.reason if d else None, "decision_code": d.why.code if d else None,
                 "decision_args": d.why.args if d else None, "room": m.room(),
                 "thermostat": m.thermostat_sp(), "thermostat_entity": m.conf.get(CONF_THERMOSTAT), "storage_kwh": round(m.storage_e, 1),
                 "paused_until": datetime.fromtimestamp(m.mem.pause_until, tz=dt_util.UTC).isoformat() if m.mem.pause_until else None,
                 "away_until": datetime.fromtimestamp(m.mem.away_until, tz=dt_util.UTC).isoformat() if m.is_away() else None,
                 "away_min": m.settings().away_min if m.is_away() else None,
                 "comfort": s.comfort, "day_min": s.day_min, "night_min": s.night_min, "store_max": s.store_max,
                 "lowest_setpoint": s.sp_min, "day_from": int(m.conf[CONF_DAY_FROM]), "day_to": int(m.conf[CONF_DAY_TO]),
                 "weekly_comfort": bool(m.conf.get(schedule.ENABLED)),
                 "comfort_schedule": {day: schedule.format_day(periods) for day, periods in m.conf.get(schedule.WEEK, {}).items()},
                 "max_above_room": s.max_above_room, "gas_boiler_hours": m.boiler_hours, "hybrid": m.hybrid, "rooms": m.room_status,
                 # the plan held (stick.py): made afresh at, for this reason; between such moments only worked out again
                 "plan_made": datetime.fromtimestamp(m.commit.at, tz=dt_util.UTC).isoformat() if m.commit is not None else None,
                 "plan_made_why": m.plan_why, "fallback": m.fallback,
                 # for the card: the unit's runs, the room the last hours, the weekly periods as minutes
                 "pump_runs": m.run_stats(time.time()),
                 "room_recent": [[e["ts"], e["T"]] for e in m.hour_log[-7:] if e.get("T") is not None],
                 "comfort_week": m.conf.get(schedule.WEEK) or None}
        if p:
            attrs["start"] = datetime.fromtimestamp(m.plan_at - m.plan_at % 3600, tz=dt_util.UTC).isoformat() if m.plan_at else None
            attrs["price_horizon_hours"] = len(m.plan_tariff)
            attrs["price_limited_until"] = (datetime.fromtimestamp(int(m.plan_at // 3600) * 3600 + len(m.plan_tariff) * 3600,
                                                                  tz=dt_util.UTC).isoformat()
                                            if m.plan_at is not None and len(m.plan_tariff) < 36 else None)
            # per hour: setpoint, room expected, kWh, price the planner uses (ct; the battery's refill cost when the
            # battery supplies), import tariff (ct), legacy guessed flag (new plans contain only known tariffs)
            tar, gss = m.plan_tariff, m.plan_guess
            attrs["plan"] = [[h.sp, round(h.t_end, 1), round(h.kwh, 2), round(h.price * 100, 1),
                              round(tar[i] * 100, 1) if i < len(tar) else None, 1 if i < len(gss) and gss[i] else 0]
                             for i, h in enumerate(p.hours)]
            attrs["day_hours"] = [1 if h.day else 0 for h in m.plan_hours[:len(p.hours)]]
            attrs["comfort_masks"] = [h.comfort_mask for h in m.plan_hours[:len(p.hours)]]
            attrs["own_kw"] = [round(h.own_kw, 2) for h in m.plan_hours[:len(p.hours)]]      # own solar to use, per hour
            # why each hour is what it is (code + values, worded by the card), from the room the plan expects then
            room = m.room()
            if room is not None:
                why = planner.explain_hours(p, m.plan_hours, room, s, m.pump, m.house, m.conf.get(CONF_EMITTER, "floor") == "floor")
                attrs["plan_why"] = [[r.code, r.args] for r in why]
            attrs["cost_24h"] = round(p.cost, 2) if len(p.hours) >= 24 else None
            attrs["steady_cost_24h"] = round(p.baseline_cost, 2) if len(p.hours) >= 24 else None
            attrs["kwh_24h"] = round(p.kwh, 1) if len(p.hours) >= 24 else None
        return attrs


class _Money(RoostEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_suggested_display_precision = 2

    @property
    def native_unit_of_measurement(self) -> str:
        return _cur(self.hass)


class SavingNext24hSensor(_Money):
    _attr_icon = "mdi:piggy-bank-outline"

    def __init__(self, mgr) -> None:
        super().__init__(mgr, "saving_next_24h")

    @property
    def native_value(self):
        p = self.mgr.plan
        return round(p.saving, 2) if p and p.breakdown.get("quality", {}).get("valid", True) else None

    @property
    def extra_state_attributes(self):
        p = self.mgr.plan
        return {"basis": "model_estimate", "quality": p.breakdown.get("quality") if p else None,
                "model_estimate": round(p.saving, 3) if p else None}


class SavingYesterdaySensor(_Money):
    _attr_icon = "mdi:piggy-bank"

    def __init__(self, mgr) -> None:
        super().__init__(mgr, "saving_yesterday")

    @property
    def native_value(self):
        day = (dt_util.now().date() - timedelta(days=1)).isoformat()
        return self.mgr.saving_days.get(day)

    @property
    def extra_state_attributes(self):
        day = (dt_util.now().date() - timedelta(days=1)).isoformat()
        stats = self.mgr.day_stats.get(day, {})
        return {"day": day, "basis": "validated_model_estimate", "quality": stats.get("quality"),
                "model_estimate": stats.get("model_saving")}


class SavingMonthSensor(_Money):
    _attr_icon = "mdi:piggy-bank"
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, mgr) -> None:
        super().__init__(mgr, "saving_month")

    @property
    def native_value(self):
        return self.mgr.saving_month()

    @property
    def extra_state_attributes(self):
        today = dt_util.now().date()
        month = today.isoformat()[:7]
        accepted = sorted(k for k in self.mgr.saving_days if k.startswith(month))
        excluded = sorted(k for k, v in self.mgr.day_stats.items() if k.startswith(month) and v.get("saving") is None
                          and k not in accepted)
        # the completed days of this month, from the first day Roost kept anything (not before it was installed)
        first = min(list(self.mgr.day_stats) + list(self.mgr.saving_days) + [today.isoformat()])
        expected = [(today - timedelta(days=n)).isoformat() for n in range(1, today.day)]
        expected = [d for d in expected if d >= first]
        absent = sorted(d for d in expected if d not in accepted and d not in excluded)
        reasons = {d: (self.mgr.day_stats.get(d, {}).get("quality") or {}).get("reasons", []) for d in excluded}
        return {"basis": "validated_model_estimates", "included_days": accepted, "excluded_days": excluded,
                "absent_days": absent, "days_expected": len(expected), "partial": bool(excluded or absent),
                "day_reasons": reasons}

    @property
    def last_reset(self):
        n = dt_util.now()
        return n.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class CostTodaySensor(_Money):
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:cash"

    def __init__(self, mgr) -> None:
        super().__init__(mgr, "cost_today")

    @property
    def native_value(self):
        return round(self.mgr.cost_today, 2)

    @property
    def extra_state_attributes(self):
        # heating electricity without any known price is left out of the cost, not counted as free
        return {"unpriced_kwh": round(self.mgr.unpriced_kwh, 3)}

    @property
    def last_reset(self):
        return dt_util.start_of_local_day()


class EnergyTodaySensor(RoostEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 1
    _attr_entity_registry_enabled_default = False

    def __init__(self, mgr) -> None:
        super().__init__(mgr, "energy_today")

    @property
    def native_value(self):
        return round(self.mgr.kwh_today, 2)


class EnergyValueSensor(RoostEntity, SensorEntity):
    _attr_entity_registry_visible_default = False      # for the card and the diagnostics; hidden in lists
    _attr_icon = "mdi:cash-clock"
    _attr_suggested_display_precision = 3
    _attr_entity_registry_enabled_default = False

    def __init__(self, mgr) -> None:
        super().__init__(mgr, "energy_value")

    @property
    def native_unit_of_measurement(self) -> str:
        return f"{_cur(self.hass)}/kWh"

    @property
    def native_value(self):
        h = self.mgr.plan_hours
        return round(h[0].p_grid, 4) if h else None

    @property
    def extra_state_attributes(self):
        h = self.mgr.plan_hours
        return {"own_solar_kw": round(h[0].own_kw, 2), "own_solar_value": round(h[0].p_own, 4)} if h else None


class HouseModelSensor(RoostEntity, SensorEntity):
    """How well the learned house model predicts a day (°C); the house's numbers in the attributes."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:home-analytics"
    _unrecorded_attributes = frozenset({"learning"})

    def __init__(self, mgr) -> None:
        super().__init__(mgr, "house_model")

    @property
    def native_value(self):
        return self.mgr.house.error_t

    @property
    def extra_state_attributes(self):
        h = self.mgr.house
        return {"heat_loss_w_per_k": round(h.H * 1000), "wind_w_per_k_per_m_s": round(h.Hw * 1000, 1), "storage_kwh_per_k": round(h.C, 1),
                "floor_lag_h": round(h.lag, 2), "solar_gain_m2": round(h.g, 2), "internal_gain_kw": round(h.internal, 2),
                "time_constant_h": round(h.time_constant_h), "balance_error_kw": h.error_balance, "days": h.days,
                "heating_days": h.heating_days, "source": h.source,
                "sun_facade": {90.0: "east", 135.0: "south-east", 180.0: "south", 225.0: "south-west", 270.0: "west"}.get(h.sun_facade, h.sun_facade)
                if h.sun_vertical > 0 else "horizontal", "sun_on_facade_share": h.sun_vertical,
                "internal_gain_per_hour_kw": h.profile, "building": _building(self.mgr.building), "learning": self.mgr.learn_info}


def _building(b: dict | None) -> dict | None:
    """Opt-in building register data, without the location."""
    if not b or b.get("none"):
        return None
    walls: dict[str, float] = {}
    for az, m in b.get("walls") or []:
        name = ("north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west")[int(((az + 22.5) % 360) // 45)]
        walls[name] = round(walls.get(name, 0.0) + m, 1)
    return {"construction_year": b.get("year"), "floor_area_m2": b.get("area_m2"), "outside_walls_m": walls}


class HeatPumpModelSensor(RoostEntity, SensorEntity):
    _attr_entity_registry_visible_default = False      # for the card and the diagnostics; hidden in lists
    """COP the model expects at 7 °C outside and 3 kW of heat."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:heat-pump-outline"

    def __init__(self, mgr) -> None:
        super().__init__(mgr, "heat_pump_model")

    @property
    def native_value(self):
        return round(self.mgr.pump.cop(7.0, 3.0), 2)

    @property
    def extra_state_attributes(self):
        p = self.mgr.pump
        return {"alpha": p.alpha, "beta": p.beta, "gamma": p.gamma, "outdoor_sensor_bias": p.bias,
                "max_output_kw_at_0": round(p.pmax(0.0), 1), "max_output_kw_at_10": round(p.pmax(10.0), 1), "hours": p.hours, "source": p.source,
                **_response(p)}


def _response(p) -> dict:
    """How the unit responds to the thermostat, and its hot water hours."""
    now = dt_util.now()
    today = [p.dhw_share(now.weekday(), h) for h in range(24)]
    return {"demand_share_of_loss": p.a, "demand_kw_per_degree": p.k, "heats_towards_setpoint_plus": round(p.offset, 1),
            "follows_per_hour": p.follow, "thermostat_reads_vs_room": p.th_diff, "lowest_output_kw": p.q_min or None,
            "cop_while_cycling": p.cyc, "response_hours": p.resp_hours, "response_error_kwh": p.resp_error, "response_source": p.resp_source,
            "hot_water_hours_today": [h for h, x in enumerate(today) if x >= 0.2], "hot_water_weeks": p.dhw_weeks}


class RoomExpectedSensor(RoostEntity, SensorEntity):
    """The room temperature the plan expects in 6 hours: with the room sensor in a history graph, how well Roost
    predicts (the card's look back shows the same)."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:home-thermometer-outline"

    def __init__(self, mgr) -> None:
        super().__init__(mgr, "room_expected_6h")

    @property
    def native_value(self):
        p = self.mgr.plan
        return round(p.hours[5].t_end, 2) if p and len(p.hours) > 5 else None


class HeatPlannedSensor(RoostEntity, SensorEntity):
    """The heat the plan has the heat pump deliver this hour (kWh)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "kWh"
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:radiator"

    def __init__(self, mgr) -> None:
        super().__init__(mgr, "heat_planned")

    @property
    def native_value(self):
        p = self.mgr.plan
        return round(p.first.heat, 2) if p and p.first else None


class PlanAccuracySensor(RoostEntity, SensorEntity):
    """How close the plan comes to what happens: the room 6 hours ahead (°C, root mean square), from the nightly
    replay of the last days with the setpoints that were really on the thermostat."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:target"

    def __init__(self, mgr) -> None:
        super().__init__(mgr, "plan_accuracy")

    @property
    def native_value(self):
        return self.mgr.check.get("rmse_6h")

    @property
    def extra_state_attributes(self):
        m = self.mgr
        return {**{k: v for k, v in m.check.items()}, "ready_to_steer": m.ready, "still_missing": m.ready_missing,
                "correction_kw": m.corr_kw, "correction_hours": m.corr_n, **_response(m.pump)}


IMPORT_STATES = ["not_yet", "importing", "done", "waiting", "failed", "no_heat_pump"]


class ImportSensor(RoostEntity, SensorEntity):
    _attr_entity_registry_visible_default = False      # for the card and the diagnostics; hidden in lists
    """Status of the import of the heat pump's history from the statistics (translated states; details in the attributes)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:database-import-outline"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = IMPORT_STATES

    def __init__(self, mgr) -> None:
        super().__init__(mgr, "history_import")

    @property
    def native_value(self):
        i = self.mgr.import_info
        status = str(i.get("status") or "")
        if self.mgr.importing:
            return "importing"
        if i.get("done"):
            return "done"
        if status.startswith("waiting"):
            return "waiting"
        if status.startswith("failed"):
            return "failed"
        if status.startswith("no Quatt"):
            return "no_heat_pump"
        return "not_yet"

    @property
    def extra_state_attributes(self):
        done, total, end = self.mgr.import_progress()
        return {**self.mgr.import_info, "progress": f"{done}/{total}" if total else None,
                "expected_done": end.isoformat(timespec="minutes") if end else None}


class ImportProgressSensor(RoostEntity, SensorEntity):
    _attr_entity_registry_visible_default = False      # for the card and the diagnostics; hidden in lists
    """How far the import is (% of the months; the expected end in the attributes)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:progress-download"
    _attr_native_unit_of_measurement = "%"

    def __init__(self, mgr) -> None:
        super().__init__(mgr, "import_progress")

    @property
    def native_value(self):
        done, total, _end = self.mgr.import_progress()
        if self.mgr.import_info.get("done"):
            return 100
        return round(100 * done / total) if total else None

    @property
    def extra_state_attributes(self):
        done, total, end = self.mgr.import_progress()
        return {"months_done": done, "months": total, "expected_done": end.isoformat(timespec="minutes") if end else None}


class HeatingCurveSensor(RoostEntity, SensorEntity):
    """The heating curve the house needs (issue #1 follow-up): the flow temperature at 0 °C outside as the state, the
    five points (outdoor -10 … 10 °C) with the flow the unit made there as attributes."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:chart-bell-curve-cumulative"
    _unrecorded_attributes = frozenset({"points", "current", "extrapolated", "cloud"})
    _attr_entity_registry_visible_default = False     # for the card (Curve view) and automations; hidden in lists

    def __init__(self, mgr) -> None:
        super().__init__(mgr, "heating_curve")

    @property
    def native_value(self):
        a = self.mgr.curve_advice
        v = a.flow_at(0.0) if a else None
        return round(v, 1) if v is not None else None

    @property
    def extra_state_attributes(self):
        a = self.mgr.curve_advice
        out: dict = {"control": "opentherm", "current": None}
        if a:
            out.update({"points": a.points, "room": a.room, "cycling_from": a.cycling_from, "reliable": a.reliable,
                        "days": a.days, "hours": a.hours, "out_min": a.out_min, "out_max": a.out_max,
                        "heat_loss_w_per_k": round(a.ua_kw * 1000), "emitter_w_per_k": round(a.k_kw * 1000), "n": a.n,
                        "margin_kw": a.margin_kw, "base_kw": a.base_kw, "extrapolated": a.extrapolated,
                        "measured_by": a.measured_by, "cloud": a.cloud, "cold_hour": a.cold_hour,
                        "ua_kw": a.ua_kw, "k_kw": a.k_kw})
        return out
