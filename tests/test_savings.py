"""Savings must be an explicitly validated estimate, including the cases reported in issue #5."""
import os
import sys
from dataclasses import replace

sys.path.insert(0, os.path.dirname(__file__))
from core import load, run_all  # noqa: E402

savings, planner, model, heatpump = (load(n) for n in ("savings", "planner", "model", "heatpump"))
START = 1_800_000_000 // 3600 * 3600


def observed_day(n=24, actual=4.0, simulated=None, saving=-0.15):
    entries = [{"ts": START + i * 3600, "T": 20.5, "T_end": 20.5, "e": actual / n} for i in range(n)]
    bd = {"saving": saving, "kwh": actual if simulated is None else simulated, "short": 0.0, "b_short": 0.0,
          "hours": [{"t": 20.5} for _ in entries]}
    return entries, bd


def test_actual_0134_kwh_is_not_a_valid_308_kwh_day():
    """A real 23 October: meter 0.134 kWh, replay 3.08 kWh, displayed saving -0.188 EUR."""
    entries, bd = observed_day(actual=0.134, simulated=3.08, saving=-0.188)
    quality = savings.assess_day(entries, bd, 24, START, True)
    published = savings.publish(bd, quality)
    assert quality["reasons"] == ["energy_mismatch"]
    assert published["saving"] is None and published["model_saving"] == -0.188
    assert quality["measured_kwh"] == 0.134 and quality["modeled_kwh"] == 3.08


def test_no_heating_is_not_a_valid_positive_model_saving():
    """20 October: the same protection applies to a positive estimate from nonexistent heating."""
    entries, bd = observed_day(actual=0.0, simulated=1.87, saving=0.04)
    quality = savings.assess_day(entries, bd, 24, START, True)
    assert not quality["valid"] and savings.publish(bd, quality)["saving"] is None


def test_valid_negative_saving_is_not_clamped_to_zero():
    entries, bd = observed_day(saving=-0.35)
    quality = savings.assess_day(entries, bd, 24, START, True)
    assert quality["valid"] and quality["status"] == "validated_estimate"
    assert savings.publish(bd, quality)["saving"] == -0.35


def test_temperature_uses_hour_end_and_can_reject_a_bad_replay():
    entries, bd = observed_day()
    for e in entries:
        e["T"] = 19.0       # these are starts; explicit observed ends take precedence
    assert savings.assess_day(entries, bd, 24, START, True)["valid"]
    for e in entries:
        e["T_end"] = 21.2
    assert "temperature_mismatch" in savings.assess_day(entries, bd, 24, START, True)["reasons"]


def test_complete_short_and_long_local_days_and_duplicate_hour():
    for n in (23, 24, 25):
        entries, bd = observed_day(n)
        assert savings.assess_day(entries, bd, n, START, True)["valid"]
        entries[-1]["ts"] = entries[-2]["ts"]
        assert "incomplete_day" in savings.assess_day(entries, bd, n, START, True)["reasons"]


def test_missing_meter_data_and_context_are_not_silently_zero():
    entries, bd = observed_day()
    entries[3].pop("e")
    q = savings.assess_day(entries, bd, 24, START, False)
    assert {"missing_measurements", "missing_context"} <= set(q["reasons"])


def test_nonfinite_measurements_are_not_accepted():
    entries, bd = observed_day()
    entries[3]["e"] = float("nan")
    assert "missing_measurements" in savings.assess_day(entries, bd, 24, START, True)["reasons"]
    entries, bd = observed_day()
    bd["kwh"] = None
    assert "energy_mismatch" in savings.assess_day(entries, bd, 24, START, True)["reasons"]


def test_extra_rooms_and_unequal_comfort_are_not_a_valid_reference():
    assert savings.comparison(0, 0)["valid"]
    assert savings.comparison(0, 0, extra_rooms=4)["reasons"] == ["extra_rooms"]
    assert savings.comparison(9.47, 6.62)["reasons"] == ["comfort_mismatch"]
    entries, bd = observed_day()
    assert savings.assess_day(entries, bd, 24, START, True, settings_changed=True)["reasons"] == ["settings_changed"]


def test_replay_propagates_pump_output_and_uses_observed_mean_setpoints():
    house = model.HouseModel()
    hp = heatpump.HeatPumpModel(follow=0.1)
    entries = [{"ts": START + i * 3600, "T": 20.5, "E": 1.0, "w": 0.0,
                "sp": 21.5 if i < 6 else 19.0, "t_out": 5.0, "p_grid": 0.3, "day": True} for i in range(24)]
    slow = planner.replay_day(house, hp, planner.Settings(), entries)
    fast = planner.replay_day(house, replace(hp, follow=1.0), planner.Settings(), entries)
    assert abs(slow[0] - fast[0]) > 0.01
    means = [{**e, "sp_mean": 20.5} for e in entries]
    replaced = [{**e, "sp": 20.5} for e in entries]
    assert planner.replay_day(house, hp, planner.Settings(), means) == planner.replay_day(house, hp, planner.Settings(), replaced)


if __name__ == "__main__":
    run_all(dict(globals()))
