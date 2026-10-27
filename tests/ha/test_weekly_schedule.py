"""The actual HA form, planner inputs, control minimum and daily context."""
from copy import deepcopy
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from unittest.mock import patch
import pytest
from homeassistant.util import dt as dt_util
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from custom_components.roost_quatt import schedule, planner, value
from .test_config_flow import COMFORT


async def open_comfort(hass,entry):
    flow=await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(flow["flow_id"],{"next_step_id":"comfort"})


def form(**days):
    return {**deepcopy(COMFORT),schedule.SECTION:{"enabled":True,**days}}


async def test_weekly_form_stores_canonical_periods_and_empty_days(hass,entry):
    flow=await open_comfort(hass,entry)
    result=await hass.config_entries.options.async_configure(flow["flow_id"],form(monday="07:00-09:00,17:30-22:00",saturday="09:00-24:00"))
    assert result["type"] is FlowResultType.MENU
    assert entry.options[schedule.ENABLED] is True
    assert entry.options[schedule.WEEK]["monday"]==[[420,540],[1050,1320]]
    assert entry.options[schedule.WEEK]["tuesday"]==[]
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"next_step_id":"comfort"})
    # Reopen and disable: the typed schedule survives for reuse.
    disabled=form(monday="07:00-09:00,17:30-22:00",saturday="09:00-24:00")
    disabled[schedule.SECTION]["enabled"]=False
    await hass.config_entries.options.async_configure(flow["flow_id"],disabled)
    assert entry.options[schedule.ENABLED] is False
    assert entry.options[schedule.WEEK]["monday"]==[[420,540],[1050,1320]]


async def test_invalid_schedule_never_changes_options(hass,entry):
    before=dict(entry.options)
    flow=await open_comfort(hass,entry)
    result=await hass.config_entries.options.async_configure(flow["flow_id"],form(sunday="22:00-02:00",monday="01:00-03:00"))
    assert result["type"] is FlowResultType.FORM and result["errors"]=={"base":"invalid_schedule"}
    assert dict(entry.options)==before


async def test_unrelated_options_keep_the_weekly_schedule(hass,entry):
    flow=await open_comfort(hass,entry)
    await hass.config_entries.options.async_configure(flow["flow_id"],form(monday="06:30-08:30"))
    expected=entry.options[schedule.WEEK]
    flow=await hass.config_entries.options.async_init(entry.entry_id)
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"next_step_id":"house"})
    await hass.config_entries.options.async_configure(flow["flow_id"],{"thermostat":"climate.living_room","emitter":"floor","use_bag":False})
    assert entry.options[schedule.ENABLED] and entry.options[schedule.WEEK]==expected


async def test_runtime_quarters_follow_local_weekday_and_current_control_minimum(hass,entry,monkeypatch):
    m=entry.runtime_data
    c=m.conf
    c.update({schedule.ENABLED:True,schedule.WEEK:schedule.normalise({"monday":"07:30-09:00"}),"day_min":20.5,"night_min":18.5})
    monkeypatch.setattr(type(m),"conf",property(lambda self:c))
    old=dt_util.DEFAULT_TIME_ZONE
    dt_util.set_default_time_zone(ZoneInfo("Europe/Amsterdam"))
    try:
        now=datetime(2026,10,26,6,0,tzinfo=timezone.utc)  # Monday 07:00 local
        base=int(now.timestamp())
        m._weather={base+i*3600:(5.,0.,3.5) for i in range(3)}
        hours=m._hours_ahead(now,[value.HourPrices(.3,.3,0,"grid")]*3,[.3]*3)
        assert hours[0].comfort_mask==(False,False,True,True)
        assert hours[1].comfort_mask==(True,)*4
        assert hours[2].comfort_mask==(False,)*4
        assert not m.is_day(dt_util.as_local(now))
        assert m.is_day(dt_util.as_local(now.replace(minute=30)))
        m.mode="shadow";m.plan_hours=hours;m.plan_at=now.timestamp()   # v0.8.0: the plan for this hour
        with patch("custom_components.roost_quatt.manager.control.decide",wraps=__import__("custom_components.roost_quatt.control",fromlist=["decide"]).decide) as decide:
            await m._async_control(now.timestamp())
            assert decide.call_args.args[4]==18.5
            await m._async_control(now.replace(minute=30).timestamp())
            assert decide.call_args.args[4]==20.5
    finally:
        dt_util.set_default_time_zone(old)


async def test_legacy_card_hours_cannot_silently_override_enabled_weekly_schedule(hass,entry,monkeypatch):
    m=entry.runtime_data;c=m.conf;c[schedule.ENABLED]=True
    monkeypatch.setattr(type(m),"conf",property(lambda self:c))
    with pytest.raises(ServiceValidationError):
        await m.async_set_settings(day_from=8)


async def test_weekly_change_is_frozen_and_invalidates_mixed_day(hass,entry,monkeypatch):
    m=entry.runtime_data;c=m.conf
    c.update({schedule.ENABLED:True,schedule.WEEK:schedule.normalise({"monday":"07:00-09:00"})})
    monkeypatch.setattr(type(m),"conf",property(lambda self:c))
    now=dt_util.utcnow().replace(minute=0,second=0,microsecond=0)
    # Match this fixture's actual local weekday so the captured schedule is unambiguous.
    m.hour_log=[];m.day_contexts={}
    m._weather[int(now.timestamp())]=(6.,0.,3.5)
    m.plan_hours=[planner.HourIn(6,3.5,0,.3,.3)]
    m.plan_at=now.timestamp()
    m._log_hour(now)
    day=dt_util.as_local(now).date().isoformat()
    assert m.day_contexts[day]["comfort_schedule"]==schedule.context(c)
    frozen=deepcopy(m.day_contexts[day]["comfort_schedule"])
    # Replace, do not mutate, exactly as an HA options update does.
    c[schedule.WEEK]=schedule.normalise({"monday":"17:00-22:00"})
    later=now+__import__("datetime").timedelta(hours=1)
    m._weather[int(later.timestamp())]=(6.,0.,3.5)
    m.plan_at=later.timestamp()
    m._log_hour(later)
    assert m.day_contexts[day]["settings_changed"] is True
    assert m.day_contexts[day]["comfort_schedule"]==frozen
