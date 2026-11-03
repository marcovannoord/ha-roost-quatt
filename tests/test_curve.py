"""Heating curve advice: the house's need, the emitters and the five points of the Weheat app."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core import load, run_all  # noqa: E402

curve = load("curve")
history = load("history")
model = load("model")

UA, BASE, K, N, ROOM = 0.2, -0.5, 0.18, 1.1, 20.5      # kW/°C, kW, kW/°C^n, floor
DAY0 = 20000 * 86400


def _house(days: int = 60, noise: float = 0.0, seed: int = 1):
    """A house that needs UA·(room − outdoor) + BASE, heated steadily by a floor that gives K·(flow − room)^N."""
    rnd = random.Random(seed)
    rows, flows = [], {}
    for d in range(days):
        t_out = -2.0 + 12.0 * (d % 15) / 14               # -2 … 10 °C
        q = max(0.0, UA * (ROOM - t_out) + BASE + rnd.gauss(0, noise))
        for h in range(24):
            ts = DAY0 + d * 86400 + h * 3600
            rows.append(model.HourRow(ts=ts, T=ROOM, T_out=t_out, Q=q, heating_s=3600.0 if q >= 0.5 else 0.0))
            if q > 0:
                flows[ts] = ROOM + (q / K) ** (1 / N)
    return rows, flows


def test_learns_the_house_and_the_floor():
    rows, flows = _house()
    a = curve.advise(rows, flows, "floor", ROOM)
    assert a is not None
    assert abs(a.ua_kw - UA) < 0.005 and abs(a.base_kw - BASE) < 0.05, (a.ua_kw, a.base_kw)
    assert abs(a.k_kw - K) < 0.005 and a.n == N
    assert a.reliable and a.days == 60 and a.margin_kw < 0.01


def test_the_line_stays_on_or_above_the_need():
    rows, flows = _house(noise=0.15)
    a = curve.advise(rows, flows, "floor", ROOM, q_min=2.0)
    assert a.margin_kw > 0.05                                    # a spread: the line goes up for it
    need = lambda t: ROOM + ((UA * (ROOM - t) + BASE) / K) ** (1 / N)       # noqa: E731
    top = a.cycling_from
    assert top is not None and abs(top - (ROOM - (2.0 - BASE) / UA)) < 0.5   # need = lowest output: ≈ 8 °C
    t = -20.0
    while t <= top:
        assert a.flow_at(t) >= need(t) - 0.01, (t, a.flow_at(t), need(t))
        t += 0.5
    ys = [y for _x, y, _m in a.points if y is not None]
    assert ys == sorted(ys, reverse=True)                        # never warmer towards milder weather
    assert all(p[1] is not None for p in a.points)               # a value for every point of the app
    assert a.points[-1][1] == curve._up(ROOM)                     # 25 °C: no heat needed, water at room temperature
    assert a.points[2][1] >= need(15.0) - 0.01                    # 15 °C, in the cycling zone: still covers the need
    assert -20.0 in a.extrapolated and a.points[1][2] is not None   # 9 °C: what the unit made there (measured)
    assert 0 < len(a.cloud) <= curve.CLOUD_MAX and a.cold_hour == -2.0      # the steady hours for the graph; coldest heated hour


def test_margin_from_the_cold_days():
    """Mild days spread far more (sun, people): the margin comes from the cold days, which shape the curve."""
    rows, flows = _house(noise=0.0)
    rnd = random.Random(3)
    out = []
    for r in rows:      # a lot of spread only on the mild days (above 5 °C)
        out.append(model.HourRow(ts=r.ts, T=r.T, T_out=r.T_out, Q=r.Q + (rnd.choice((-0.8, 0.8)) if r.T_out > 5 and (r.ts // 86400) % 2 else 0.0),
                                 heating_s=r.heating_s))
    a = curve.advise(out, flows, "floor", ROOM)
    assert a.margin_kw < 0.05, a.margin_kw


def test_radiators_need_warmer_water_than_a_floor():
    rows, flows = _house()
    floor = curve.advise(rows, flows, "floor", ROOM)
    # the same measurements read as radiators: k comes out differently, the curve still meets the same need
    rad = curve.advise(rows, flows, "radiators", ROOM)
    assert rad.n == 1.3 and abs(rad.flow_at(0.0) - floor.flow_at(0.0)) < 1.5


def test_measured_under_opentherm_or_the_curve():
    """The Weheat logs say per hour whether an OpenTherm thermostat asked a water temperature: the measured flows are
    labelled with what controlled the unit."""
    rows, flows = _house()
    steady = {r.ts for r in rows if r.Q >= 0.5}
    assert curve.advise(rows, flows, "floor", ROOM, opentherm=steady).measured_by == "opentherm"
    assert curve.advise(rows, flows, "floor", ROOM, opentherm={DAY0 - 3600}).measured_by == "heating_curve"
    assert curve.advise(rows, flows, "floor", ROOM).measured_by is None          # imported before: not known


def test_cycling_limit_is_measured():
    """Share of interrupted heating hours per outdoor degree, as measured on a Blackbird P80: past half from 8 °C."""
    share = {-2: 16, -1: 9, 0: 8, 1: 5, 2: 17, 3: 18, 4: 18, 5: 30, 6: 36, 7: 49, 8: 53, 9: 59, 10: 60, 11: 66, 12: 76}
    rows = []
    for t, pct in share.items():
        for i in range(100):
            rows.append(model.HourRow(ts=DAY0 + len(rows) * 3600, T=20.5, T_out=t + 0.5, Q=1.0,
                                      heating_s=1800.0 if i < pct else 3600.0))
    assert curve.cycling_limit(rows) == 8.0
    assert curve.cycling_limit(rows[:300]) is None                   # three degrees seen: too little to judge


def test_too_little_data_gives_no_advice():
    rows, flows = _house(days=10)
    assert curve.advise(rows, flows, "floor", ROOM) is None
    rows, _ = _house()
    assert curve.advise(rows, {}, "floor", ROOM) is None          # no flow temperatures: no emitter


def test_kept_over_a_restart():
    rows, flows = _house()
    a = curve.advise(rows, flows, "floor", ROOM, q_min=2.0)
    b = curve.CurveAdvice.from_dict(a.as_dict())
    assert b == a and curve.CurveAdvice.from_dict(None) is None and curve.CurveAdvice.from_dict({"x": 1}) is None


def test_flow_and_return_from_the_weheat_logs():
    h = history.weheat_hours([{"timeBucket": "2026-10-20T06:00:00Z", "tWaterOutAverage": 31.4, "tWaterInAverage": 27.9,
                               "heatPumpStateHeating": 3600}], [])
    v = next(iter(h.values()))
    assert (v["flow"], v["ret"]) == (31.4, 27.9) and v["rpm"] is None
    assert curve.flows_from_hours(h) == {next(iter(h)): 31.4}


def test_reading_logs_again_keeps_the_energy():
    """A read of the hourly logs alone (to add fields) on top of hours with their energy: the energy stays."""
    t = "2026-01-10T06:00:00Z"
    have = history.weheat_hours([{"timeBucket": t, "tRoomAverage": 20.4, "heatPumpStateHeating": 3600}],
                                [{"timeBucket": t, "totalEOutHeating": 3.1, "totalEInHeating": 0.8, "totalEInDhw": 0.2}])
    history.merge_hours(have, history.weheat_hours([{"timeBucket": t, "tRoomAverage": 20.4, "tWaterOutAverage": 33.0}], []))
    v = next(iter(have.values()))
    assert (v["q"], v["e"], v["dhw_e"], v["flow"]) == (3.1, 0.8, 0.2, 33.0)


def test_extra_weheat_fields_kept_compactly():
    """Thermostat demand, backup heater, compressor limits, errors: kept when not zero, left out when zero or empty."""
    h = history.weheat_hours([{"timeBucket": "2026-10-20T06:00:00Z", "thermostatStateOn": 3600, "controlBridgeStatusElectricHeater": 0,
                               "rpmLimiterSilentHours": 1800.0, "dtcError": None, "tThermostatSetpointAverage": 31.27}],
                             [{"timeBucket": "2026-10-20T06:00:00Z", "totalEOutHeating": 2.0, "totalEInStandby": 0.012,
                               "totalEOutDhw": 0}])
    v = next(iter(h.values()))
    assert (v["th_on_s"], v["lim_silent_s"], v["th_water"], v["standby_e"]) == (3600.0, 1800.0, 31.27, 0.01)
    assert not {"heater_s", "err_s", "dhw_q", "boiler_s"} & set(v)


if __name__ == "__main__":
    run_all(dict(globals()))
