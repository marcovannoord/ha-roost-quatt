"""The Quatt side: which entities, what the CIC's state means, hours from the long-term statistics (quatt.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core import load, run_all  # noqa: E402

quatt = load("quatt")
heatpump = load("heatpump")

HUB = "01JABCDEF"
DUO = [(f"{HUB}:cic:qc.supervisoryControlMode", "sensor.cic_qc_supervisory_control_mode_code"),
       (f"{HUB}:cic:computedHeatPower", "sensor.cic_heat_power"),
       (f"{HUB}:cic:computedPower", "sensor.cic_total_power"),
       (f"{HUB}:cic:computedPowerInput", "sensor.cic_total_power_input"),
       (f"{HUB}:cic:computedQuattCop", "sensor.cic_total_quatt_cop"),
       (f"{HUB}:heatpump_1:hp1.powerInput", "sensor.heatpump_1_power_input"),
       (f"{HUB}:heatpump_1:hp1.temperatureOutside", "sensor.heatpump_1_temperature_outside"),
       (f"{HUB}:heatpump_1:hp1.temperatureWaterOut", "sensor.heatpump_1_water_out"),
       (f"{HUB}:heatpump_2:hp2.powerInput", "sensor.heatpump_2_power_input"),
       (f"{HUB}:heatpump_2:hp2.temperatureWaterOut", "sensor.heatpump_2_water_out"),
       (f"{HUB}:thermostat:thermostat.otFtControlSetpoint", "sensor.thermostat_control_setpoint"),
       (f"{HUB}:thermostat:thermostat.otFtRoomSetpoint", "sensor.thermostat_room_setpoint"),
       (f"{HUB}:thermostat:thermostat.otFtRoomTemperature", "sensor.thermostat_room_temperature"),
       (None, "sensor.no_unique_id")]


def test_roles_from_unique_ids():
    r = quatt.resolve(DUO)
    assert quatt.is_quatt(r)
    assert r["power_out"] == "sensor.cic_heat_power"                     # measured flow × ΔT before what the units report
    assert r["power_out_hp"] == "sensor.cic_total_power"
    assert r["water_out"] == "sensor.heatpump_2_water_out"               # a Duo: the second unit's outlet goes to the house
    assert r["water_setpoint"] == "sensor.thermostat_control_setpoint"
    assert "boiler_power" not in r and "units" not in r
    assert quatt.units(r) == 2 and quatt.units(r, 1.0) == 1
    single = quatt.resolve([x for x in DUO if ":heatpump_2:" not in (x[0] or "")])
    assert single["water_out"] == "sensor.heatpump_1_water_out" and quatt.units(single) == 1
    assert not quatt.is_quatt(quatt.resolve(DUO[1:]))                     # without the CIC's state: not usable


def test_names_choose_the_profile():
    assert heatpump.profile_for("Quatt Duo") == "quatt_duo" and heatpump.profile_for("Quatt") == "quatt"
    duo, one = heatpump.HeatPumpModel.for_profile("quatt_duo"), heatpump.HeatPumpModel.for_profile("quatt")
    assert duo.pmax(0.0) > 1.8 * one.pmax(0.0)


def test_device_entries_old_and_new():
    from types import SimpleNamespace as NS
    assert quatt.device_entry_ids(NS(config_entry_id="a", config_entries={"a"})) == ["a"]     # HA 2026: one entry
    assert quatt.device_entry_ids(NS(config_entries={"b"})) == ["b"]                        # older HA


def test_cic_state():
    assert quatt.pump_state("2", 1.2) == "heating"
    assert quatt.pump_state("2", 0.05) == "standby"                      # the CIC says heating, the units have not started
    assert quatt.pump_state("2") == "heating"
    assert quatt.pump_state("0") == quatt.pump_state("1") == "standby"
    assert quatt.pump_state("4") == "boiler" and quatt.pump_state("6") == "cooling" and quatt.pump_state("99") == "fault"
    assert quatt.pump_state("Heating - heatpump only", 1.0) == "heating"   # the text sensor works too
    assert quatt.pump_state(None) is None and quatt.pump_state("nonsense") is None


def test_heating_seconds_from_statistics():
    assert quatt.heating_seconds(0.01, 0.0, 0.02) == 0.0                  # standby all hour
    assert quatt.heating_seconds(1.1, 0.9, 1.3) == 3600.0                 # never stopped
    s = quatt.heating_seconds(0.5, 0.01, 1.2)                             # cycled: on about half the hour
    assert 1500 < s < 2000
    assert quatt.heating_seconds(None, None, None) is None
    assert quatt.heating_seconds(0.5, None, None) == 3600.0


def test_hours_from_statistics():
    t = 1768471200
    stats = {"power_in": {t: {"mean": 0.9, "min": 0.8, "max": 1.0}, t + 3600: {"mean": 0.01, "min": 0.0, "max": 0.02},
                          t + 7200: {"mean": 0.5}},
             "power_out": {t: {"mean": 3.6}, t + 3600: {"mean": 0.0}},
             "water_out": {t: {"mean": 33.0}, t + 3600: {"mean": 24.0}},
             "water_setpoint": {t: {"mean": 31.0, "max": 34.0}, t + 3600: {"mean": 10.0, "max": 10.0}},
             "thermostat_setpoint": {t: {"mean": 20.5}},
             "boiler_power": {t: {"mean": 0.0, "max": 0.0}}}
    h = quatt.hours_from_stats(stats, {})
    assert set(h) == {t, t + 3600}                                         # no heat for the third hour: left out
    assert h[t] == {"q": 3.6, "e": 0.9, "dhw_e": 0.0, "dhw_s": 0.0, "heating_s": 3600.0, "flow": 33.0, "th_water": 31.0, "sp": 20.5}
    assert h[t + 3600]["heating_s"] == 0.0 and "flow" not in h[t + 3600]   # standing water says nothing about the flow
    assert "th_water" not in h[t + 3600]                                   # the thermostat asked for no heat
    w = quatt.hours_from_stats({"power_in": {t: {"mean": 900.0, "min": 800.0, "max": 1000.0}}, "power_out": {t: {"mean": 3600.0}}},
                               {"power_in": 0.001, "power_out": 0.001})
    assert w[t]["q"] == 3.6 and w[t]["e"] == 0.9                          # W converted


def test_standby_is_not_heating_electricity():
    """As a heat pump's own meter for heating: the ~10 W the units take standing still is left out."""
    t0 = 1768471200
    pin = {t0 + 3600 * i: {"mean": 0.010, "min": 0.009, "max": 0.012} for i in range(30)}          # 30 idle hours
    pin[t0 + 3600 * 30] = {"mean": 1.0, "min": 0.8, "max": 1.2}                                      # all hour on
    pin[t0 + 3600 * 31] = {"mean": 0.4, "min": 0.01, "max": 1.0}                                     # cycled
    pout = {t: {"mean": 0.0 if v["max"] < 0.1 else 3.0} for t, v in pin.items()}
    assert quatt.standby_kw(pin) == 0.01 and quatt.standby_kw(dict(list(pin.items())[:10])) is None
    h = quatt.hours_from_stats({"power_in": pin, "power_out": pout}, {})
    assert h[t0]["e"] == 0.0 and h[t0]["standby_e"] == 0.01
    assert h[t0 + 3600 * 30]["e"] == 1.0 and "standby_e" not in h[t0 + 3600 * 30]     # ran all hour: no standby
    c = h[t0 + 3600 * 31]
    assert 0 < c["standby_e"] < 0.01 and abs(c["e"] + c["standby_e"] - 0.4) < 1e-9
    few = quatt.hours_from_stats({"power_in": {t0: pin[t0]}, "power_out": {t0: pout[t0]}}, {}, standby=0.01)
    assert few[t0]["e"] == 0.0                                                          # the standby measured before


def test_a_boiler_hour():
    t = 1768471200
    h = quatt.hours_from_stats({"power_in": {t: {"mean": 1.0}}, "power_out": {t: {"mean": 3.0}},
                                "boiler_power": {t: {"mean": 2.0, "max": 8.0}}}, {})
    assert h[t]["boiler_s"] == 900


def test_merge_keeps_what_roost_counted():
    t = 1768471200
    have = {t: {"heating_s_live": 1200}}
    quatt.merge_hours(have, {t: {"q": 2.0, "heating_s": 3600.0}})
    assert have[t] == {"heating_s_live": 1200, "q": 2.0, "heating_s": 3600.0}


def test_live_hour_counts_seconds():
    lh = quatt.LiveHour()
    t0 = 1768471200
    assert lh.feed(t0, 0, "standby") is None
    t = t0
    for i in range(29):                                     # 29 ticks of 2 min: about half heating
        t += 120
        assert lh.feed(t, 120, "heating" if i % 2 else "standby") is None
    closed = lh.feed(t0 + 3600 + 60, 60, "heating")
    assert closed is not None and closed[0] == t0 and 1700 <= closed[1]["heating_s_live"] <= 1900
    assert lh.feed(t0 + 7300, 120, "heating") is None      # an hour mostly unseen (HA off) gives nothing


if __name__ == "__main__":
    run_all(dict(globals()))
