"""Looking back: a day in numbers, from the hourly log. Pure Python.

The hourly log (manager.hour_log) holds per hour the room at its start, what the thermostat had and what Roost
planned, the reason, the room predicted for that hour 6 and 1 hours earlier, the heat and electricity of the hour and
its cost. The card's look back draws from it; this sums a day for the day report.
"""
from __future__ import annotations


def _r(v: float | None, n: int = 2) -> float | None:
    return None if v is None else round(v, n)


def day_stats(entries: list[dict], comfort: float, by_hand: int = 0, cost_replay: float | None = None,
              steady_replay: float | None = None) -> dict:
    """One day: electricity, heat, cost, comfort, thermostat changes and how well the plan predicted the room."""
    kwh = sum(e.get("e") or 0.0 for e in entries)
    heat = sum(e.get("q") or 0.0 for e in entries)
    cost = sum(e.get("cost") or 0.0 for e in entries)
    temps = [e["T"] for e in entries if e.get("T") is not None]
    day = [e for e in entries if e.get("day") and not e.get("away") and e.get("T") is not None]
    weight = lambda e: sum(e["comfort_mask"])/4 if e.get("comfort_mask") is not None else 1.0
    deficit = sum(max(0.0, comfort - e["T"])*weight(e) for e in day)
    below = sum(60*weight(e) for e in day if e["T"] < comfort - 0.3)
    sps = [e.get("sp_t") for e in entries if e.get("sp_t") is not None]
    changes = sum(1 for a, b in zip(sps, sps[1:]) if abs(a - b) >= 0.25)
    err = [e["T"] - e["p6"] for e in entries if e.get("p6") is not None and e.get("T") is not None]
    out = {"hours": len(entries), "kwh": _r(kwh), "heat_kwh": _r(heat), "cost": _r(cost, 3),
           "cop": _r(heat / kwh) if kwh > 0.5 else None, "deficit_ch": _r(deficit), "below_min": below,
           "low": _r(min(temps)) if temps else None, "changes": changes, "by_hand": by_hand,
           "pred_mae": _r(sum(abs(x) for x in err) / len(err)) if err else None,
           "pred_max": _r(max(err, key=abs)) if err else None, "pred_hours": len(err)}
    if cost_replay is not None and steady_replay is not None:
        out.update(saving=_r(steady_replay - cost_replay, 3), steady=_r(steady_replay, 3))
    return out
