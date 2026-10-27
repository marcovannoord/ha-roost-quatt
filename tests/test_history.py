"""The heat pump's hourly history kept by Roost (history.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from core import load, run_all  # noqa: E402

history = load("history")


def test_a_gas_boiler_that_ran_makes_a_hybrid():
    """#5: a hybrid heat pump is told apart by the hours its gas boiler ran (the CIC's boiler heat)."""
    hours = {t: {"q": 1.0} for t in range(100)}
    assert history.boiler_hours(hours) == 0
    hours.update({1: {"boiler_s": 1200}, 2: {"boiler_s": 900}, 3: {"boiler_s": 60}, 4: {"boiler_s": 3600}})
    assert history.boiler_hours(hours) == 3 >= history.HYBRID_HOURS          # 60 s is not running


def test_boiler_type_decides_a_hybrid():
    """A boiler type known as
    1 (none) says it is no hybrid. 2/3 (on/off, OpenTherm) is one without any boiler hours; 0 or unknown: the hours."""
    assert history.is_hybrid(1, 5) is False
    assert history.is_hybrid(2, 0) is True and history.is_hybrid(3, 0) is True
    assert history.is_hybrid(0, 5) is True and history.is_hybrid(None, 5) is True
    assert history.is_hybrid(None, 2) is False


if __name__ == "__main__":
    run_all(dict(globals()))
