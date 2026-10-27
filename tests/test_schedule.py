"""Weekly comfort boundaries and the planner's actual quarter-hour obligations."""
from datetime import datetime, timedelta, timezone
from dataclasses import replace
from zoneinfo import ZoneInfo
import os,sys
sys.path.insert(0,os.path.dirname(__file__))
from core import load, run_all
schedule=load("schedule")
planner=load("planner")
model=load("model")
heatpump=load("heatpump")


def conf(**days):
    return {schedule.ENABLED:True,schedule.WEEK:schedule.normalise(days),"day_from":7,"day_to":22}


def test_multiple_blocks_and_empty_days():
    c=conf(monday="07:00-09:00, 17:30-22:00")
    at=lambda h,m=0:datetime(2026,10,26,h,m)
    assert schedule.is_comfort(c,at(7))
    assert not schedule.is_comfort(c,at(9))
    assert not schedule.is_comfort(c,at(17,29))
    assert schedule.is_comfort(c,at(17,30))
    assert not schedule.is_comfort(c,at(22))
    assert not schedule.is_comfort(c,datetime(2026,10,27,8))


def test_overnight_including_sunday_week_wrap():
    c=conf(sunday="22:00-02:00",monday="07:00-09:00")
    assert schedule.is_comfort(c,datetime(2026,10,25,23))
    assert schedule.is_comfort(c,datetime(2026,10,26,1,59))
    assert not schedule.is_comfort(c,datetime(2026,10,26,2))
    assert schedule.is_comfort(c,datetime(2026,10,26,8))


def test_full_day_and_adjacent_blocks():
    c=conf(monday="00:00-12:00, 12:00-24:00")
    assert schedule.is_comfort(c,datetime(2026,10,26,0))
    assert schedule.is_comfort(c,datetime(2026,10,26,23,59))
    assert not schedule.is_comfort(c,datetime(2026,10,27,0))


def test_invalid_times_and_overlap_are_rejected():
    invalid=[{"monday":s} for s in ["7-9","07:00-07:00","24:00-01:00","07:10-09:00",
                                   "07:00-24:15","07:00-09:00,08:00-10:00","07:00-09:00,"]]
    invalid += [{"sunday":"22:00-02:00","monday":"01:00-03:00"},
                {"monday":[[False,60]]},{"monday":[[420.,540]]},{"monday":[[420,-15]]},
                {"noday":"07:00-09:00"}]
    for week in invalid:
        try:schedule.normalise(week)
        except ValueError:pass
        else:raise AssertionError(week)


def test_canonical_roundtrip_and_disabled_legacy_default():
    week=schedule.normalise({"monday":"7:00-9:30, 22:00-2:00"})
    assert schedule.format_day(week["monday"])=="07:00-09:30, 22:00-02:00"
    assert schedule.normalise(week)==week
    c=conf(monday="")
    c[schedule.ENABLED]=False
    assert schedule.is_comfort(c,datetime(2026,10,26,7))
    assert not schedule.is_comfort(c,datetime(2026,10,26,22))


def test_dst_both_repeated_hours_and_spring_gap_use_local_wall_time():
    zone=ZoneInfo("Europe/Amsterdam")
    c=conf(sunday="02:00-03:00")
    for fold in (0,1):
        t=datetime(2026,10,25,2,30,tzinfo=zone,fold=fold)
        assert schedule.is_comfort(c,t)
    # Spring: 01:45 local jumps directly to 03:00; the absent period is not shifted.
    before=datetime(2026,3,29,0,45,tzinfo=timezone.utc)
    after=before+timedelta(minutes=15)
    assert not schedule.is_comfort(c,before.astimezone(zone))
    assert not schedule.is_comfort(c,after.astimezone(zone))


def stationary():
    return planner.Simulator(model.HouseModel(C=20,H=.1,g=0,lag=0,internal=0,Hw=0),
                             heatpump.HeatPumpModel(a=0,k=0),
                             planner.Settings(comfort=21,day_min=19,night_min=19,penalty_soft=2))


def test_partial_hour_comfort_penalty_and_reference_deficit_match():
    sim=stationary()
    h=planner.HourIn(t_out=20,wind=3.5,rad=0,p_grid=.3,p_own=.3,day=True,
                     comfort_mask=(False,False,True,True))
    T,E,c,e,q,pen=sim.hour(20,0,18,h,0)
    assert abs(T-20)<1e-12 and abs(sim.comfort_deficit-.5)<1e-12
    assert abs(pen-1)<1e-12
    assert planner._deficit(T,h,sim.s,sim.comfort_deficit)==.5
    _,_,_,_,_,pen=sim.hour(20,0,18,replace(h,away=True),0)
    assert pen==0 and sim.comfort_deficit==0
    trace={}
    planner.comparable_steady(sim,[h],20,0,0,sim.m,.5,trace)
    assert trace["deficit"]==.5


def test_weekly_night_terminal_target_does_not_buy_unrequested_comfort():
    sim=stationary()
    h=planner.HourIn(20,3.5,0,.3,.3,day=False,comfort_mask=(False,)*4)
    assert planner._end_value(sim,[h],21)(19,0)==0
    assert planner._end_value(sim,[replace(h,away=True)],21)(sim.s.away_min,0)==0
    assert planner._end_value(sim,[replace(h,comfort_mask=None)],21)(19,0)>0


def test_slow_floor_preheats_before_future_comfort_block():
    house=model.HouseModel(C=14,H=.16,g=0,lag=1,internal=.2,Hw=0)
    hp=heatpump.HeatPumpModel(a=.9,k=1.5,offset=.2,follow=.35,th_diff=0)
    s=planner.Settings(comfort=21,day_min=21,night_min=18,sp_min=18,store_max=22)
    hours=[planner.HourIn(3,3.5,0,.25,.25,day=i>=4,
                           comfort_mask=(i>=4,)*4) for i in range(8)]
    planned=planner.plan(house,hp,s,hours,20.6,1,18,8,0)
    absent=planner.plan(house,hp,s,[replace(h,day=False,comfort_mask=(False,)*4) for h in hours],20.6,1,18,8,0)
    assert sum(h.kwh for h in planned.hours[:4])>sum(h.kwh for h in absent.hours[:4])+.05
    assert any(h.sp>18 for h in planned.hours[:4])


def test_lookback_counts_only_scheduled_quarters():
    lookback=load("lookback")
    entries=[{"T":20,"day":True,"comfort_mask":[False,False,True,True]},
             {"T":20,"day":True,"comfort_mask":[True]*4,"away":True}]
    stats=lookback.day_stats(entries,21)
    assert stats["deficit_ch"]==.5 and stats["below_min"]==30


if __name__=="__main__":run_all(dict(globals()))
