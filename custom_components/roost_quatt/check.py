"""Does the plan come true? Self-check of the models, and a correction from the last hours. Pure Python.

Self-check (every night): the last days replayed with the planner's own simulator and the setpoints that were really
on the thermostat (so it also works in shadow mode, while something else steers): from every hour, 1, 6 and 24 hours
ahead, the predicted room temperature against the measured one, and over 24 hours the heat and electricity against
the meters. That tests the whole chain the planner relies on: house model, response to the thermostat, hot water and
COP. Roost is ready to steer when it predicts well over enough heating hours and the unit follows the thermostat.

Correction (every plan): when the room was warmer or colder than predicted in the last dark hours (visitors, a door,
cooking, a model that is off), the planner gets that as extra heat in kW, fading out over the coming hours. The nightly
learning takes over what lasts. Sunny hours are left out: until v0.7.7 their surprise was carried ahead as extra sun for
a day, which made the forecasts 6–24 hours ahead worse on a year of the author's data (and changed nothing in the
simulations). A room reading in half degrees (only the thermostat) gives no correction: a step of 0.5 °C is 7 kW in an
hour, so the correction would only follow the rounding.
"""
from __future__ import annotations

from bisect import bisect_right
from datetime import datetime
from math import ceil

from .heatpump import HeatPumpModel
from .model import HouseModel, HourRow, unfollowed
from .planner import HourIn, Settings, Simulator
from .window import reading_step

HORIZONS = (1, 6, 24)
CHECK_DAYS = 7
CHECK_BACK_DAYS = 60       # an older week with enough heating is checked when the last week had too little
# mild weather: judged on the last heating weeks instead (within a year)
WINTER_WEEK_HOURS = 60     # a heating week: at least this many heating hours the thermostat asked for
WINTER_WEEKS = 8           # the newest ones checked: two months, so one odd week does not decide
WINTER_PASS = 4            # at least this many have to pass on their own, and the medians over all of them
MONDAY = 4 * 86400         # the epoch was a Thursday: weeks from Monday 00:00 UTC, so they do not shift every night
WARMUP = 6
# ready to steer
READY_HEATING_HOURS = 30
READY_RMSE_6H = 0.5        # °C
READY_HEAT_RATIO = 0.3     # predicted heat within ±30 % of the meters
# correction
CORR_HOURS = 8             # residuals of the last hours
CORR_HALF_LIFE = 3.0       # hours: weight of older residuals
CORR_FADE = 6.0            # hours: half-life of the correction in the plan
CORR_MAX = 1.0             # kW
CORR_SUN_RAD = 0.02        # kW/m² on the facade: below it an hour counts as dark
CORR_COARSE = 0.3          # °C: a room reading that changes in steps this large or more gives no correction
# when ready
ETA_MONTH_S = 5            # one month of history from Home Assistant's statistics: seconds
ETA_MONTH_LOGS_S = 5
ETA_LEARN_S = 900          # learning and the self-check after the import


def _hourin(r: HourRow) -> HourIn:
    return HourIn(t_out=r.T_out, wind=r.wind, rad=r.rad, p_grid=0.0, p_own=0.0, dhw=min(1.0, r.dhw_s / 3600), hour=r.hour)


def check_end(rows: list[HourRow], house: HouseModel, hp: HeatPumpModel, days: int = CHECK_DAYS, back: int = CHECK_BACK_DAYS) -> int | None:
    """End of the window to check: the last hour, or, when the last days had too little heating (mild weather, or just
    after the import), the end of the newest window of `days` days in the last `back` days that had enough (with the
    setpoint known). Not further back: a spring week says little about steering in autumn (the unit may stop heating
    above an outdoor limit, the sun is different) — then Roost waits for the heating season."""
    unf = unfollowed(rows, house, hp)
    heat = sorted(r.ts for r in rows if r.Q > 0.3 and r.sp is not None and r.ts not in unf)
    if not heat:
        return None
    last = max(r.ts for r in rows)
    span = days * 86400
    if len(heat) - bisect_right(heat, last - span) >= READY_HEATING_HOURS:
        return last
    for i in range(len(heat) - 1, -1, -1):           # windows ending at a heating hour, newest first
        end = heat[i]
        if end < last - back * 86400:
            break
        if i + 1 - bisect_right(heat, end - span) >= READY_HEATING_HOURS:
            return end
    return None


def self_check(rows: list[HourRow], house: HouseModel, hp: HeatPumpModel, days: int = CHECK_DAYS) -> dict:
    idx = idx_all = {r.ts: r for r in rows}
    if not idx:
        return {"hours": 0}
    unf = unfollowed(rows, house, hp)
    last = max(idx)
    end = check_end(rows, house, hp, days)
    older = end is not None and end < last - 86400
    if older:
        last = end
        idx = {t: r for t, r in idx.items() if t <= end + 24 * 3600}     # the 24-hour horizon may run past the end
    first = last - days * 86400
    keep = max(0.0, house.lag) / (1 + max(0.0, house.lag))
    sim = Simulator(house, hp, Settings())
    err: dict[int, list[float]] = {h: [] for h in HORIZONS}
    heat_p = heat_m = elec_p = elec_m = 0.0
    for t in sorted(x for x in idx if first <= x <= last):
        r0, prev = idx[t], idx.get(t - 3600)
        if prev is None or r0.sp is None or t in unf:
            continue
        E = 0.0                                   # storage at the start, from the heat of the hours before
        if any(t - 3600 * k not in idx for k in range(1, WARMUP + 1)):
            continue
        for k in range(WARMUP, 0, -1):
            E = (E + idx[t - 3600 * k].Q) * keep
        T = (prev.T + r0.T) / 2
        w = prev.Q                                # the output follows the demand with a delay, from what it gave before
        hq = he = mq = me = 0.0
        for k in range(max(HORIZONS)):
            r = idx.get(t + 3600 * k)
            if r is None or r.sp is None or r.ts in unf:
                break                             # an hour the unit heated without the thermostat: not the model's
            T, E, _c, e, q, _p = sim.hour(T, E, r.sp, _hourin(r), w)
            w = sim.w_end
            hq, he, mq, me = hq + q, he + e, mq + r.Q, me + r.E
            nxt = idx.get(t + 3600 * (k + 1))
            measured = (r.T + nxt.T) / 2 if nxt else None    # hourly means: the end of hour k lies between them
            if k + 1 in err and measured is not None:
                err[k + 1].append(T - measured)
            if k + 1 == max(HORIZONS):
                heat_p, heat_m, elec_p, elec_m = heat_p + hq, heat_m + mq, elec_p + he, elec_m + me
    out: dict = {"hours": len(err[1]), "days": days,
                 "heating_hours": sum(1 for x in idx.values() if first <= x.ts <= last and x.Q > 0.3 and x.ts not in unf),
                 "unfollowed_hours": sum(1 for t in unf if first <= t <= last)}
    if older:
        out["window_end"] = last          # the last days had too little heating: an older week was checked
    newest = max(idx_all)
    out["heating_per_day"] = round(sum(1 for t, x in idx_all.items() if t > newest - 3 * 86400 and x.Q > 0.3 and t not in unf) / 3, 1)
    for h, xs in err.items():
        if xs:
            out[f"rmse_{h}h"] = round((sum(x * x for x in xs) / len(xs)) ** 0.5, 3)
            out[f"bias_{h}h"] = round(sum(xs) / len(xs), 3)
            out[f"n_{h}h"] = len(xs)
    if heat_m > 1.0:
        out["heat_ratio"] = round(heat_p / heat_m, 3)
    if elec_m > 0.3:
        out["elec_ratio"] = round(elec_p / elec_m, 3)
    return out


def winter_check(rows: list[HourRow], house: HouseModel, hp: HeatPumpModel) -> dict | None:
    """The self-check on the newest heating weeks of the last year (WINTER_WEEK_HOURS heating hours the thermostat
    asked for), for when the last week says too little: in mild weather a week has few heating hours, while how well
    Roost predicts in heating weather is what matters for steering. -> {"weeks", "passed", "rmse_6h", "heat_ratio",
    "until"} (medians over the weeks checked), or None without heating weeks."""
    if not rows:
        return None
    unf = unfollowed(rows, house, hp)
    heat = sorted(r.ts for r in rows if r.Q > 0.3 and r.sp is not None and r.ts not in unf)
    last = max(r.ts for r in rows)
    span = CHECK_DAYS * 86400
    ends = []
    this_week = (last - MONDAY) // span * span + MONDAY            # fixed weeks: the same verdict tomorrow
    for k in range(1, 53):
        end = this_week - (k - 1) * span
        if len(heat) and end > last - 365 * 86400 and bisect_right(heat, end) - bisect_right(heat, end - span) >= WINTER_WEEK_HOURS:
            ends.append(end)
        if len(ends) == WINTER_WEEKS:
            break
    if not ends:
        return None
    results = [self_check([r for r in rows if end - span - 86400 <= r.ts <= end], house, hp) for end in ends]  # + warm-up
    ok = [readiness(c, None)[0] for c in results]

    def median(key):
        xs = sorted(c[key] for c in results if c.get(key) is not None)
        return round(xs[len(xs) // 2], 3) if xs else None
    return {"weeks": len(results), "passed": sum(ok), "rmse_6h": median("rmse_6h"), "heat_ratio": median("heat_ratio"),
            "until": max(ends)}


def winter_ok(w: dict | None) -> bool:
    """The heating weeks say ready: the medians within the limits, and at least WINTER_PASS weeks passing on their own
    (so one odd week does not flip the verdict, and two good weeks do not decide it)."""
    if not w or w.get("passed", 0) < WINTER_PASS:
        return False
    rmse, ratio = w.get("rmse_6h"), w.get("heat_ratio")
    return rmse is not None and rmse <= READY_RMSE_6H and ratio is not None and abs(ratio - 1) <= READY_HEAT_RATIO


def readiness(chk: dict, following: bool | None, lever: bool = True, winter: dict | None = None) -> tuple[bool, list[str]]:
    """Ready to steer? -> (ready, what is still missing as short codes). lever: the setpoint moves the heat pump.
    winter (winter_check): when the last week had too little heating, the last heating weeks decide."""
    missing = [] if lever else ["lever"]
    if chk.get("heating_hours", 0) < READY_HEATING_HOURS and winter_ok(winter):
        if following is False:
            missing.append("following")
        return not missing, missing
    if chk.get("heating_hours", 0) < READY_HEATING_HOURS:
        missing.append("heating_hours")
    rmse = chk.get("rmse_6h")
    if rmse is None or rmse > READY_RMSE_6H:
        missing.append("temperature")
    ratio = chk.get("heat_ratio")
    if ratio is None or abs(ratio - 1) > READY_HEAT_RATIO:
        missing.append("heat")
    if following is False:
        missing.append("following")
    return not missing, missing


def import_done_at(imp: dict, now: float, logs_only: bool = False) -> float:
    """When a running import is expected to finish: a month per half hour after the last month that came in (per two
    minutes when only the hourly logs are read)."""
    left = max(0, imp.get("months", 0) - imp.get("months_done", 0))
    try:
        since = datetime.fromisoformat(imp["at"]).timestamp() if imp.get("at") else now
    except (TypeError, ValueError):
        since = now
    return max(now, since + left * (ETA_MONTH_LOGS_S if logs_only else ETA_MONTH_S))


def eta(missing: list[str], chk: dict, imp: dict, now: float, next_check: float) -> tuple[str, float | None]:
    """When Roost expects to be ready to steer -> (what it waits for, unix time or None). Codes: ready; lever and
    following (a setting of the heat pump, no time); import (after the import from the statistics and the learning that follows);
    heating (more heating hours, the nightly check after them); heating_season (no heating now); check (the next
    nightly self-check, which may pass or not)."""
    if not missing:
        return "ready", None
    if "lever" in missing:
        return "lever", None
    if "following" in missing:
        return "following", None
    if imp.get("status") == "importing":
        return "import", import_done_at(imp, now) + ETA_LEARN_S
    if "heating_hours" in missing:
        per_day = chk.get("heating_per_day", 0.0)
        if per_day * chk.get("days", CHECK_DAYS) < READY_HEATING_HOURS:
            return "heating_season", None           # at this pace a week never has enough: when it gets colder
        days = ceil(max(0, READY_HEATING_HOURS - chk.get("heating_hours", 0)) / per_day)
        return "heating", next_check + max(0, days - 1) * 86400
    return "check", next_check


def correction(entries: list[dict], house: HouseModel, hp: HeatPumpModel, now_ts: float) -> tuple[float, int]:
    """Heat the model missed in the last dark hours, from the hourly log: each hour replayed from its measured start
    with the setpoint that was on the thermostat. -> (kW, hours used); + = the room got warmer than predicted. Only
    hours without sun count (people, a door, a stove): what sunny hours missed is the sun model's, and the nightly
    learning takes that over. Nothing when the room reading changes in steps of CORR_COARSE or more."""
    sim = Simulator(house, hp, Settings())
    by_ts = {e["ts"]: e for e in entries}
    recent = [e for e in entries if now_ts - e["ts"] <= (CORR_HOURS + 1) * 3600]
    if reading_step(e.get("T") for e in recent) >= CORR_COARSE:
        return 0.0, 0
    res: list[tuple[float, float]] = []          # (kW missed, weight)
    for e in recent:
        nxt = by_ts.get(e["ts"] + 3600)
        sp = e.get("sp_t")
        if nxt is None or sp is None or "dhw" not in e:
            continue
        if e.get("window") or nxt.get("window"):
            continue                                # airing: not something the model missed
        if e.get("rad", 0.0) >= CORR_SUN_RAD:
            continue
        h = HourIn(t_out=e["t_out"], wind=e.get("wind", 3.5), rad=e.get("rad", 0.0), p_grid=0.0, p_own=0.0, dhw=e["dhw"],
                   hour=e.get("hour", -1))
        w0 = (by_ts.get(e["ts"] - 3600) or {}).get("q")      # heat the hour before: where the output starts
        T1 = sim.hour(e["T"], e.get("E", 0.0), float(sp), h, w0)[0]
        kw = (nxt["T"] - T1) * house.C              # °C over one hour × kWh/K = kW
        res.append((kw, 0.5 ** ((now_ts - nxt["ts"]) / 3600 / CORR_HALF_LIFE)))
    n = len(res)
    if n < 2:
        return 0.0, n
    kw = sum(k * w for k, w in res) / sum(w for _, w in res) * n / (n + 1)
    return round(max(-CORR_MAX, min(CORR_MAX, kw)), 3), n


def fade(kw: float, hours_ahead: int) -> float:
    return kw * 0.5 ** (hours_ahead / CORR_FADE)
