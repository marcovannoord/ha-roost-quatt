"""Quality of a modelled saving, independently checked against the observed day. Pure Python.

Both alternatives must use one model; replacing just Roost's simulated cost by its meter reading would assign
all model error to one side. Keep the model result for diagnosis, but do not publish it as a validated estimate
when the replay misses the real day or the reference has different comfort obligations.
"""
from __future__ import annotations

from math import isfinite

ENERGY_ABS_KWH = 0.5
ENERGY_REL = 0.25
ROOM_MAE_K = 0.5
COMFORT_TOLERANCE_CH = 0.05
OBSERVED_S = 3000          # seconds of an hour Roost must have seen for its measurements to count


def comparison(short: float, baseline_short: float, extra_rooms: int = 0) -> dict:
    """The current reference models the main room only. Never claim whole-house equivalence for extra rooms."""
    reasons = []
    if extra_rooms:
        reasons.append("extra_rooms")
    if abs(short - baseline_short) > COMFORT_TOLERANCE_CH + 1e-9:
        reasons.append("comfort_mismatch")
    return {"valid": not reasons, "status": "model_estimate" if not reasons else "not_comparable", "reasons": reasons}


def assess_day(entries: list[dict], breakdown: dict, expected_hours: int, start_ts: int,
               frozen_context: bool, extra_rooms: int = 0, settings_changed: bool = False) -> dict:
    """Conservative, explicit acceptance bounds, not a confidence interval or a proof of causal savings.

An energy mismatch must exceed both 0.5 kWh and 25% of measured heating electricity to reject a day. Compare
the replay's end temperatures with measured ends, not with the temperatures at each hour's start. Require a
complete local day; UTC timestamps distinguish the repeated hour when daylight saving time ends.
"""
    out = comparison(breakdown.get("short", 0), breakdown.get("b_short", 0), extra_rooms)
    reasons = list(out["reasons"])
    if not frozen_context:
        reasons.append("missing_context")
    if settings_changed:
        reasons.append("settings_changed")
    expected = [start_ts + i * 3600 for i in range(expected_hours)]
    if [e.get("ts") for e in entries] != expected:
        reasons.append("incomplete_day")
    # an hour Roost saw only part of (a restart within it): its measured use is short (entries before v0.8.1 have no obs)
    if any(e.get("partial") or (e.get("obs") is not None and e["obs"] < OBSERVED_S) for e in entries):
        reasons.append("partial_hours")

    def number(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v)

    metered = [e["e"] for e in entries if number(e.get("e")) and e["e"] >= 0]
    actual = sum(metered)
    simulated = breakdown.get("kwh", 0)
    valid_simulation = number(simulated) and simulated >= 0
    limit = max(ENERGY_ABS_KWH, ENERGY_REL * actual)
    if len(metered) != len(entries) or not entries:
        reasons.append("missing_measurements")
    elif not valid_simulation or abs(simulated - actual) > limit:
        reasons.append("energy_mismatch")
    by_ts = {e["ts"]: e for e in entries}
    errors = []
    for e, row in zip(entries, breakdown.get("hours", [])):
        observed = e.get("T_end")
        if observed is None:
            observed = by_ts.get(e["ts"] + 3600, {}).get("T")
        if number(observed) and number(row.get("t")):
            errors.append(abs(observed - row["t"]))
    mae = sum(errors) / len(errors) if errors else None
    if len(errors) < max(1, expected_hours - 1):
        if "missing_measurements" not in reasons:
            reasons.append("missing_measurements")
    elif mae > ROOM_MAE_K:
        reasons.append("temperature_mismatch")
    out.update(valid=not reasons, status="validated_estimate" if not reasons else "unreliable",
               reasons=reasons, measured_kwh=round(actual, 3), modeled_kwh=simulated,
               energy_error_kwh=round(simulated - actual, 3) if valid_simulation else None,
               energy_tolerance_kwh=round(limit, 3),
               temperature_mae=None if mae is None else round(mae, 3),
               temperature_tolerance=ROOM_MAE_K, measured_hours=len(metered), expected_hours=expected_hours,
               context="day_start" if frozen_context else "current_model_fallback")
    return out


def publish(breakdown: dict, quality: dict) -> dict:
    """Keep the raw result and its explanation; only expose the accepted estimate as `saving`."""
    raw = breakdown.get("model_saving", breakdown.get("saving"))
    return {**breakdown, "model_saving": raw, "saving": raw if quality["valid"] else None, "quality": quality}
