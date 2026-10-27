"""Why the plan changed (replan.py)."""
import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(__file__))
from core import load, run_all  # noqa: E402

replan = load("replan")
BASE = 1_800_000_000 // 3600 * 3600


def snap(at=BASE + 600, base=BASE, sp=20.5, saving=0.40, price=0.25, guess=None, t_out=5.0, room=20.5, corr=0.0,
         settings=None, neutral=False, n=24, t=20.5):
    sps = sp if isinstance(sp, list) else [sp] * n
    plan = NS(hours=[NS(sp=x, t_end=t) for x in sps], saving=saving)
    hours = [NS(t_out=t_out, rad=0.0) for _ in sps]
    prices = price if isinstance(price, list) else [price] * n
    return replan.snapshot(at, base, plan, hours, prices, guess or [False] * n, room, corr, settings or {"comfort": 20.5}, neutral)


def test_nothing_changed_is_no_line():
    assert replan.compare(snap(), snap(at=BASE + 1500), 20.5) is None
    assert replan.compare(None, snap(), 20.5) is None


def test_published_prices_change_the_plan():
    old = snap(guess=[False] * 4 + [True] * 20)
    new = snap(at=BASE + 1500, sp=21.0, saving=0.55, price=[0.25] * 4 + [0.40] * 20)
    line = replan.compare(old, new, 20.5)
    assert line["why"] == ["prices_published"] and line["sp"] == [20.5, 21.0] and line["saving"] == [0.40, 0.55]
    assert line["detail"]["prices_published"] == 20


def test_changed_prices_forecast_room_and_correction():
    old = snap()
    new = snap(at=BASE + 1500, sp=21.0, price=[0.25] * 12 + [0.30] * 12, t_out=3.0, room=19.9, corr=0.3)
    line = replan.compare(old, new, 19.9)
    assert line["why"] == ["prices_changed", "forecast", "room", "correction"], line
    assert line["detail"]["room_expected"] == 20.5 and line["detail"]["forecast_k"] == 2.0


def test_newly_published_hours_extend_a_short_plan():
    line = replan.compare(snap(n=8), snap(at=BASE + 1500, sp=21.0), 20.5)
    assert line["why"] == ["prices_published"]
    assert line["detail"]["prices_published"] == 16


def test_a_new_hour_compares_the_same_hour():
    """An hour later the old plan's second hour is the new plan's first: its setpoint is what changed or not."""
    old = snap(sp=[20.5, 21.0] + [20.5] * 22)
    assert replan.compare(old, snap(at=BASE + 3600 + 60, base=BASE + 3600, sp=[21.0] + [20.5] * 23), 20.5) is None
    line = replan.compare(old, snap(at=BASE + 3600 + 60, base=BASE + 3600, sp=20.5, saving=0.30), 20.5)
    assert line["sp"] == [21.0, 20.5] and line["why"] == ["new_hour"]


def test_saving_alone_and_settings_and_estimates():
    line = replan.compare(snap(), snap(at=BASE + 1500, saving=0.50, settings={"comfort": 21.0}, neutral=True), 20.5)
    assert line["why"] == ["settings", "estimated"]
    assert replan.compare(snap(), snap(at=BASE + 1500, saving=0.43), 20.5) is None     # 3 ct: not worth a line


def test_unexplained_saving_change_is_no_line_and_a_setpoint_change_names_the_largest_cause():
    """21-10: many lines said only 'recalculated' while the saving jumped 10-20 ct. A saving that moves on its own is
    no line now; a setpoint that changes names the largest cause, also below its threshold."""
    assert replan.compare(snap(), snap(at=BASE + 1500, saving=0.60), 20.45) is None
    line = replan.compare(snap(), snap(at=BASE + 1500, sp=21.0, room=20.35), 20.35)       # room 0.15 off: under 0.3
    assert line["why"] == ["room"] and line["detail"]["room"] == 20.35, line
    line = replan.compare(snap(), snap(at=BASE + 1500, sp=21.0), 20.5)
    assert line["why"] == ["other"], line


def test_prune_keeps_two_days():
    log = [{"ts": BASE - 3 * 86400}, {"ts": BASE - 86400}]
    assert replan.prune(log, BASE) == [{"ts": BASE - 86400}]


if __name__ == "__main__":
    run_all(dict(globals()))
