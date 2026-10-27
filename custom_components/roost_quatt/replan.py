"""Why the plan changed: the plan in force beside the new one, and what is different between what each saw
(prices published or changed, the weather forecast, the room off from what was expected, the correction from the
last hours, settings, guessed prices left out). Kept for two days, for the look back report and roost.explain_saving."""
from __future__ import annotations

SAVING_STEP = 0.05      # a change of the expected saving smaller than this is not worth a line
KEPT_S = 2 * 86400
PRICE_REL = 0.01        # a published price that moved more than 1 % changed
FORECAST_K = 1.0        # °C outdoor
FORECAST_SUN = 0.1      # kW/m²
ROOM_K = 0.3            # °C off from what the plan in force expected
CORR_KW = 0.1


def snapshot(at: float, base: int, p, hours: list, tariff: list[float], guess: list[bool], room: float,
             corr_kw: float, settings: dict, neutral: bool) -> dict:
    """What a plan was and what it saw, for the next comparison (planner.Plan, planner.HourIn per hour)."""
    n = len(p.hours)
    return {"at": round(at), "base": base, "room": round(room, 2), "sp": [h.sp for h in p.hours],
            "t": [round(h.t_end, 2) for h in p.hours], "saving": round(p.saving, 3),
            "price": [round(x, 4) for x in tariff[:n]], "guess": [bool(g) for g in guess[:n]],
            "t_out": [round(h.t_out, 1) for h in hours[:n]], "rad": [round(h.rad, 3) for h in hours[:n]],
            "corr": round(corr_kw, 3), "settings": settings, "neutral": neutral}


def _expected_now(old: dict, at: float) -> float | None:
    """The room the old plan expected at `at` (between its hour ends)."""
    t, pts = old["t"], [(old["at"], old["room"])]
    pts += [(old["base"] + (k + 1) * 3600, x) for k, x in enumerate(t)]
    for (a, x), (b, y) in zip(pts, pts[1:]):
        if a <= at <= b:
            return x + (y - x) * (at - a) / max(1.0, b - a)
    return None


def compare(old: dict | None, new: dict, room: float) -> dict | None:
    """-> a log line when the setpoint for now or the expected saving changed, with what caused it; None otherwise. A
    change of the saving alone that nothing explains (small differences in the room or the forecast add up) is no line;
    a change of the setpoint names its largest cause even when that is below its threshold."""
    if not old or not new["sp"]:
        return None
    shift = (new["base"] - old["base"]) // 3600
    if shift < 0 or shift >= len(old["sp"]):
        return None
    sp_old, sp_new = old["sp"][shift], new["sp"][0]
    if abs(sp_new - sp_old) < 0.01 and abs(new["saving"] - old["saving"]) < SAVING_STEP:
        return None
    why, detail = [], {}
    n = min(len(old["sp"]) - shift, len(new["sp"]))
    published = sum(1 for k in range(n, len(new["price"]))
                    if len(old["sp"]) < 24 and k + shift >= len(old["price"])
                    and not (new["guess"][k] if k < len(new["guess"]) else False))
    changed = 0
    for k in range(n):
        og = old["guess"][k + shift] if k + shift < len(old["guess"]) else False
        ng = new["guess"][k] if k < len(new["guess"]) else False
        if k + shift >= len(old["price"]) or k >= len(new["price"]):
            break
        po, pn = old["price"][k + shift], new["price"][k]
        if og and not ng:
            published += 1
        elif not og and not ng and abs(pn - po) > PRICE_REL * max(abs(po), 0.01):
            changed += 1
    dt = max((abs(new["t_out"][k] - old["t_out"][k + shift]) for k in range(min(n, 12))), default=0.0)
    dr = max((abs(new["rad"][k] - old["rad"][k + shift]) for k in range(min(n, 12))), default=0.0)
    exp = _expected_now(old, new["at"])
    droom = abs(room - exp) if exp is not None else 0.0
    dcorr = abs(new["corr"] - old["corr"])
    # each cause against its threshold: >= 1 counts; below, the largest still names a change of the setpoint
    size = {"forecast": max(dt / FORECAST_K, dr / FORECAST_SUN), "room": droom / ROOM_K, "correction": dcorr / CORR_KW}
    if published:
        why.append("prices_published")
        detail["prices_published"] = published
    if changed:
        why.append("prices_changed")
        detail["prices_changed"] = changed
    if new["settings"] != old["settings"]:
        why.append("settings")
    if new["neutral"] != old["neutral"]:
        why.append("estimated")
    why += [c for c in ("forecast", "room", "correction") if size[c] >= 1.0]
    if not why:
        if abs(sp_new - sp_old) < 0.01:
            return None                 # only the expected saving moved, and nothing that explains it: no line
        biggest = max(size, key=size.get)
        why.append(biggest if size[biggest] >= 0.25 else ("new_hour" if shift > 0 else "other"))
    if "forecast" in why:
        detail["forecast_k"], detail["forecast_sun"] = round(dt, 1), round(dr, 2)
    if "room" in why and exp is not None:
        detail["room"], detail["room_expected"] = round(room, 2), round(exp, 2)
    if "correction" in why:
        detail["corr"] = [old["corr"], new["corr"]]
    return {"ts": new["at"], "sp": [sp_old, sp_new], "saving": [old["saving"], new["saving"]], "why": why, "detail": detail}


def prune(log: list[dict], now: float) -> list[dict]:
    return [e for e in log if e["ts"] > now - KEPT_S]
