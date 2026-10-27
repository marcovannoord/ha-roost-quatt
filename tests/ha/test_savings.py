"""Runtime regression checks: hour boundaries, day snapshots, validation and sensor dates."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from homeassistant.util import dt as dt_util

from custom_components.roost_quatt import planner
from custom_components.roost_quatt.sensor import SavingYesterdaySensor


@pytest.fixture
def berlin_timezone():
    old = dt_util.DEFAULT_TIME_ZONE
    dt_util.set_default_time_zone(ZoneInfo("Europe/Berlin"))
    yield
    dt_util.set_default_time_zone(old)


async def test_hour_boundary_forces_plan_before_logging(entry):
    m = entry.runtime_data
    now = dt_util.utcnow().replace(minute=0, second=2, microsecond=0)
    m.plan_at = now.timestamp() - 120                 # not due on the 15-minute interval, but in the previous hour
    m.hour_log = []
    m.plan_hours = [planner.HourIn(5, 3.5, 0, 0.1, 0.1), planner.HourIn(5, 3.5, 0, 0.7, 0.7)]
    assert m.plan_hour(now).p_grid == 0.7

    async def new_plan(_now, *_args):
        m.plan_at = _now.timestamp()
        m.plan_hours = [planner.HourIn(5, 3.5, 0, 0.7, 0.7)]

    with patch("custom_components.roost_quatt.manager.dt_util.utcnow", return_value=now), \
         patch.object(m, "_async_weather", AsyncMock()), \
         patch.object(m, "_async_plan", AsyncMock(side_effect=new_plan)) as plan, \
         patch.object(m, "_async_control", AsyncMock()):
        m._weather[int(now.timestamp() // 3600 * 3600)] = (5, 0, 3.5)
        await m._async_tick(None)
    plan.assert_awaited_once()
    assert m.hour_log[-1]["p_grid"] == 0.7


async def test_cost_uses_current_hour_before_replanning(entry):
    m = entry.runtime_data
    now = dt_util.utcnow().replace(minute=0, second=2, microsecond=0)
    m.plan_at = now.timestamp() - 120
    m.plan_hours = [planner.HourIn(5, 3.5, 0, 0.1, 0.1), planner.HourIn(5, 3.5, 0, 0.7, 0.7)]
    m._cost_day = dt_util.as_local(now).date().isoformat()
    m._last_elec, m.cost_today = 10.0, 0.0
    with patch.object(m, "_num", side_effect=[11.0, 0.0]):
        m._count_cost(now)
    assert abs(m.cost_today - 0.7) < 1e-9


async def test_day_model_is_a_copy_and_is_not_replaced_by_later_learning(entry):
    m = entry.runtime_data
    now = dt_util.utcnow()
    day = dt_util.as_local(now).date().isoformat()
    m.hour_log = []
    m.plan_at = now.timestamp()
    m._weather[int(now.timestamp() // 3600 * 3600)] = (5, 0, 3.5)
    m._log_hour(now)
    original = m.day_contexts[day]["house"]["H"]
    m.house.H += 1
    m.hour_log = []
    m._log_hour(now)
    assert m.day_contexts[day]["house"]["H"] == original


async def test_bad_energy_replay_is_retained_but_not_published(entry):
    m = entry.runtime_data
    start = dt_util.start_of_local_day(dt_util.now() - timedelta(days=1))
    expected = round(((start + timedelta(days=1)).timestamp() - start.timestamp()) / 3600)
    day = start.date().isoformat()
    m.hour_log = [{"ts": int(start.timestamp()) + h * 3600, "T": 20.5, "T_end": 20.5,
                   "E": 0.0, "sp": 20.5, "sp_t": 20.5, "t_out": 5.0, "p_grid": 0.3,
                   "e": 0.134 / expected, "q": 0.7 / expected} for h in range(expected)]
    m.day_contexts[day] = {"house": m.house.as_dict(), "pump": m.pump.as_dict(),
                           "settings": vars(m.settings()), "extra_rooms": 0, "replay_version": planner.REPLAY_VERSION}
    bd = {"saving": -0.188, "kwh": 3.08, "short": 0, "b_short": 0,
          "hours": [{"t": 20.5} for _ in m.hour_log]}
    with patch("custom_components.roost_quatt.hourlog.planner.replay_day", return_value=(0.9, 0.712, bd)):
        await m._async_close_day(day)
    assert day not in m.saving_days
    assert m.saving_detail[day]["model_saving"] == -0.188
    assert m.day_stats[day]["saving"] is None
    assert m.day_stats[day]["quality"]["reasons"] == ["energy_mismatch"]


async def test_yesterday_does_not_fall_back_to_an_older_successful_day(entry):
    m = entry.runtime_data
    yesterday = (dt_util.now().date() - timedelta(days=1)).isoformat()
    older = (dt_util.now().date() - timedelta(days=2)).isoformat()
    m.saving_days = {older: 1.23}
    sensor = SavingYesterdaySensor(m)
    assert sensor.native_value is None and sensor.extra_state_attributes["day"] == yesterday


@pytest.mark.parametrize(("day", "length"), [("2026-10-25", 25), ("2026-03-29", 23)])
async def test_day_close_respects_local_daylight_saving_time(entry, berlin_timezone, day, length):
    m = entry.runtime_data
    start = dt_util.start_of_local_day(datetime.fromisoformat(day))
    m.hour_log = [{"ts": int(start.timestamp()) + h * 3600, "T": 20.5, "T_end": 20.5,
                   "E": 0, "sp": 20.5, "sp_t": 20.5, "t_out": 5, "p_grid": 0.3,
                   "e": 0.3, "q": 1.2} for h in range(length)]
    m.day_contexts[day] = {"house": m.house.as_dict(), "pump": m.pump.as_dict(),
                           "settings": vars(m.settings()), "extra_rooms": 0, "replay_version": planner.REPLAY_VERSION}
    bd = {"saving": -0.1, "kwh": length * 0.3, "short": 0, "b_short": 0,
          "hours": [{"t": 20.5} for _ in m.hour_log]}
    with patch("custom_components.roost_quatt.hourlog.planner.replay_day", return_value=(1.0, 0.9, bd)):
        await m._async_close_day(day)
    assert m.day_stats[day]["quality"]["valid"]
    assert m.day_stats[day]["quality"]["expected_hours"] == length
    assert m.saving_days[day] == -0.1
