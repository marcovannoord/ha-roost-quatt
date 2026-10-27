"""Unpublished tariffs must not participate in either planning or battery valuation."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.roost_quatt import value
from custom_components.roost_quatt.sensor import SavingNext24hSensor, SetpointSensor

from .conftest import PRICE


@pytest.fixture(autouse=True)
def mutable_test_configuration(entry, monkeypatch):
    """Change this test's configuration without reloading the integration or writing a config entry."""
    m = entry.runtime_data
    conf = m.conf
    monkeypatch.setattr(type(m), "conf", property(lambda _self: conf))


def publish(hass, now, count, price=0.30):
    base = now.replace(minute=0, second=0, microsecond=0)
    rates = [{"start": (base + timedelta(hours=i)).isoformat(),
              "end": (base + timedelta(hours=i + 1)).isoformat(), "value": price}
             for i in range(count)]
    hass.states.async_set(PRICE, str(price), {"unit_of_measurement": "EUR/kWh", "rates": rates})


@pytest.mark.parametrize("mode", ["sensor", "epex"])
async def test_old_prices_never_fill_the_unpublished_tail(hass, entry, mode):
    m = entry.runtime_data
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    base = int(now.timestamp())
    m.conf["price_mode"] = mode
    m._epex = [(base + i*3600, base + (i+1)*3600, .1) for i in range(8)]
    m.conf.update(import_mult=1., import_add=0.)
    publish(hass, now, 8)
    key = "epex_import" if mode == "epex" else PRICE
    m.price_seen[key] = {base + i*3600 - 86400: .95 for i in range(36)}
    a = m._energy(now, 36)
    assert a is not None and len(a[0].import_price) == 8
    m.price_seen[key] = {base + i*3600 - 86400: -.50 for i in range(36)}
    b = m._energy(now, 36)
    assert a == b


async def test_horizon_is_clipped_before_battery_valuation(hass, entry):
    m = entry.runtime_data
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    publish(hass, now, 10)
    m.conf.update(battery_soc="sensor.price_test_soc", battery_kwh=14., battery_kw=5.)
    hass.states.async_set("sensor.price_test_soc", "80")
    with patch("custom_components.roost_quatt.prices.value.compute", wraps=value.compute) as compute:
        inp, ev = m._energy(now, 36)
    assert len(compute.call_args.args[0].import_price) == 10
    assert len(inp.import_price) == len(ev.value) == 10


async def test_unpublished_export_prices_also_bound_the_horizon(hass, entry):
    m = entry.runtime_data
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    publish(hass, now, 10)
    m.conf["export_price"] = "sensor.price_test_export"
    rates = [{"start": now.isoformat(), "end": (now + timedelta(hours=3)).isoformat(), "value": .05}]
    hass.states.async_set("sensor.price_test_export", ".05", {"unit_of_measurement": "EUR/kWh", "rates": rates})
    inp, ev = m._energy(now, 36)
    assert len(inp.import_price) == len(inp.export_price) == len(ev.value) == 3


async def test_missing_configured_export_price_is_not_replaced_by_import(hass, entry):
    m = entry.runtime_data
    m.conf["export_price"] = "sensor.missing_export"
    assert m._energy(dt_util.utcnow(), 36) is None


async def test_a_gap_stops_planning_even_if_later_prices_exist(hass, entry):
    m = entry.runtime_data
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    publish(hass, now, 12)
    attrs = dict(hass.states.get(PRICE).attributes)
    attrs["rates"] = [r for i, r in enumerate(attrs["rates"]) if i != 5]
    hass.states.async_set(PRICE, ".30", attrs)
    inp, _ = m._energy(now, 36)
    assert len(inp.import_price) == 5


async def test_plan_extends_when_prices_are_published_and_partial_saving_is_unavailable(hass, entry):
    m = entry.runtime_data
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    publish(hass, now, 8)
    await m._async_plan(now)
    assert len(m.plan_hours) == len(m.plan.hours) == 8
    assert not any(m.plan_guess)
    assert "incomplete_forecast" in m.plan.breakdown["quality"]["reasons"]
    assert SavingNext24hSensor(m).native_value is None
    attrs = SetpointSensor(m).extra_state_attributes
    assert attrs["price_horizon_hours"] == 8 and attrs["cost_24h"] is None
    assert attrs["price_limited_until"] == (now + timedelta(hours=8)).isoformat()

    publish(hass, now, 36)
    await m._async_plan(now + timedelta(seconds=1))
    assert len(m.plan_hours) == 36 and len(m.plan.hours) == 24
    assert "incomplete_forecast" not in m.plan.breakdown["quality"]["reasons"]
    assert SetpointSensor(m).extra_state_attributes["price_limited_until"] is None


def _issue(hass, entry, kind):
    from homeassistant.helpers import issue_registry as ir
    return ir.async_get(hass).async_get_issue("roost_quatt", f"{entry.entry_id}_price_no_forecast_{kind}_{PRICE}")


async def test_a_sensor_without_forecast_or_history_plans_on_a_flat_price(hass, entry):
    """v0.8.0: not a 1-hour plan. Nothing known about the sensor yet: its current price for every hour, with a notice."""
    m = entry.runtime_data
    now = dt_util.utcnow()
    m.price_seen.pop(PRICE, None)
    hass.states.async_set(PRICE, "-0.05", {"unit_of_measurement": "EUR/kWh"})
    inp, _ = m._energy(now, 36)
    assert inp.import_price == [-.05] * 36
    assert _issue(hass, entry, "flat") is not None and _issue(hass, entry, "estimated") is None


def _history(m, now, price):
    base = int(now.timestamp() // 3600 * 3600)
    m.price_seen[PRICE] = {base - h * 3600: price(base - h * 3600) for h in range(1, 48)}
    return base


async def test_a_fixed_price_sensor_without_forecast_needs_no_notice(hass, entry):
    m = entry.runtime_data
    now = dt_util.utcnow()
    _history(m, now, lambda ts: 0.27)
    hass.states.async_set(PRICE, "0.27", {"unit_of_measurement": "EUR/kWh"})
    inp, _ = m._energy(now, 36)
    assert inp.import_price == [.27] * 36
    assert _issue(hass, entry, "flat") is None and _issue(hass, entry, "estimated") is None


async def test_a_day_night_rate_sensor_repeats_its_rates(hass, entry):
    m = entry.runtime_data
    now = dt_util.utcnow()
    night = lambda ts: m.local_hour(ts) >= 23 or m.local_hour(ts) < 7
    base = _history(m, now, lambda ts: 0.20 if night(ts) else 0.30)
    cur = 0.20 if night(base) else 0.30
    hass.states.async_set(PRICE, str(cur), {"unit_of_measurement": "EUR/kWh"})
    inp, _ = m._energy(now, 36)
    assert len(inp.import_price) == 36
    assert inp.import_price[1:] == [0.20 if night(base + i * 3600) else 0.30 for i in range(1, 36)]
    assert _issue(hass, entry, "flat") is None


async def test_a_dynamic_sensor_without_forecast_is_estimated_from_day_ahead_prices(hass, entry):
    """The sensor followed day-ahead × 1.21 + 0.10: the hours ahead come from the published day-ahead prices."""
    m = entry.runtime_data
    now = dt_util.utcnow()
    base = int(now.timestamp() // 3600 * 3600)
    epex = lambda ts: 0.05 + 0.04 * ((ts // 3600) % 7)
    m._epex = [(base + h * 3600, base + (h + 1) * 3600, epex(base + h * 3600)) for h in range(-48, 20)]
    _history(m, now, lambda ts: 1.21 * epex(ts) + 0.10)
    hass.states.async_set(PRICE, str(round(1.21 * epex(base) + 0.10, 4)), {"unit_of_measurement": "EUR/kWh"})
    inp, _ = m._energy(now, 36)
    assert len(inp.import_price) == 20                     # only as far as day-ahead prices are published
    assert inp.import_price[5] == pytest.approx(1.21 * epex(base + 5 * 3600) + 0.10, abs=1e-6)
    assert _issue(hass, entry, "estimated") is not None and _issue(hass, entry, "flat") is None


async def test_a_dynamic_sensor_that_does_not_follow_day_ahead_stays_flat(hass, entry):
    m = entry.runtime_data
    now = dt_util.utcnow()
    base = int(now.timestamp() // 3600 * 3600)
    m._epex = [(base + h * 3600, base + (h + 1) * 3600, 0.05 + 0.04 * (h % 7)) for h in range(-48, 20)]
    _history(m, now, lambda ts: 0.30 if (ts // 3600) % 5 else 0.10)     # unrelated to day-ahead
    hass.states.async_set(PRICE, "0.30", {"unit_of_measurement": "EUR/kWh"})
    inp, _ = m._energy(now, 36)
    assert inp.import_price == [.30] * 36
    assert _issue(hass, entry, "flat") is not None


async def test_fixed_contract_still_has_a_full_horizon(entry):
    m = entry.runtime_data
    m.conf.update(price_mode="fixed", fixed_price=.3, fixed_export_price=.05)
    inp, _ = m._energy(dt_util.utcnow(), 36)
    assert inp.import_price == [.3]*36 and inp.export_price == [.05]*36


async def test_missing_price_keeps_the_plan_for_an_hour_then_plans_on_a_flat_price(hass, entry):
    """v0.8.0 (R02): a short gap keeps the plan held; after FALLBACK_MIN Roost plans on one flat price instead of
    leaving the thermostat wherever the last plan put it."""
    m = entry.runtime_data
    now = dt_util.utcnow()
    assert m.plan is not None
    held = m.planned_sp(now.timestamp())
    hass.states.async_set(PRICE, "unavailable")
    await m._async_plan(now)
    assert m.reason.code == "no_price" and m.plan is not None and m.planned_sp(now.timestamp()) == held
    later = now + timedelta(minutes=61)
    await m._async_plan(later)
    assert m.fallback == "no_price" and m.plan is not None and m.reason.code == "fallback_no_price"
    assert len(set(m.plan_tariff)) == 1 and m.plan.breakdown["saving"] is None
