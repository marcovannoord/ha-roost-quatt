"""Day-ahead (EPEX) electricity prices, built in: no price sensor needed.

From Energy-Charts (Fraunhofer ISE): public, no key, per bidding zone, per quarter hour since October 2025 (per hour
before). Data under CC BY 4.0, see https://energy-charts.info. Energy-Charts limits how often one address may ask, so
Roost asks once an hour, and a little more often in the afternoon until tomorrow's prices are there.

The price a user pays (or earns) is the day-ahead price times a multiplier plus a fixed amount: in the Netherlands
for example (EPEX + purchase fee + energy tax) × 1.21 VAT = EPEX × 1.21 + (fee + tax) × 1.21. Pure Python apart from
the fetch.
"""
from __future__ import annotations

from datetime import date, timedelta

URL = "https://api.energy-charts.info/price"
ZONES = ["NL", "BE", "DE-LU", "AT", "FR", "CH", "DK1", "DK2", "NO2", "SE3", "SE4", "FI", "PL", "CZ", "HU", "SI",
         "IT-North"]                                 # bidding zones Energy-Charts serves (each checked, 15-10-2026)
COUNTRY_ZONE = {"NL": "NL", "BE": "BE", "DE": "DE-LU", "LU": "DE-LU", "AT": "AT", "FR": "FR", "CH": "CH", "DK": "DK1",
                "NO": "NO2", "SE": "SE3", "FI": "FI", "PL": "PL", "CZ": "CZ", "HU": "HU", "SI": "SI", "IT": "IT-North"}
REFRESH_S = 3600                                     # once an hour
TOMORROW_RETRY_S = 900                               # from 13:00 until tomorrow's prices are in: every quarter hour

Slot = tuple[float, float, float]                    # (start, end, currency per kWh)


def zone_for(country: str | None) -> str:
    return COUNTRY_ZONE.get((country or "").upper(), "NL")


def parse(payload: dict) -> list[Slot]:
    """Energy-Charts' {"unix_seconds": [...], "price": [... per MWh]} -> slots in currency per kWh."""
    ts, pr = payload.get("unix_seconds") or [], payload.get("price") or []
    pts = [(float(t), float(p) / 1000) for t, p in zip(ts, pr) if t is not None and p is not None]
    pts.sort()
    out: list[Slot] = []
    for i, (t, p) in enumerate(pts):
        end = pts[i + 1][0] if i + 1 < len(pts) else t + (t - pts[i - 1][0] if i else 900)
        if end > t:
            out.append((t, min(end, t + 3600), p))
    return out


def formula(v: float, mult: float, add: float) -> float:
    """What a kWh costs (or earns): day-ahead × multiplier + fixed amount."""
    return v * mult + add


def needs_refresh(slots: list[Slot], fetched_at: float | None, now_ts: float, local_hour: int, tomorrow_end_ts: float) -> bool:
    """Ask again? Once an hour; from 13:00 every quarter hour while tomorrow's prices are not there yet."""
    if fetched_at is None or not slots:
        return fetched_at is None or now_ts - fetched_at >= TOMORROW_RETRY_S
    age = now_ts - fetched_at
    if age >= REFRESH_S:
        return True
    has_tomorrow = max(s[1] for s in slots) >= tomorrow_end_ts - 3600
    return local_hour >= 13 and not has_tomorrow and age >= TOMORROW_RETRY_S


def period(today: date) -> tuple[str, str]:
    """From yesterday to the day after tomorrow (Energy-Charts' end date is exclusive)."""
    return (today - timedelta(days=1)).isoformat(), (today + timedelta(days=2)).isoformat()


async def async_fetch(session, zone: str, today: date) -> list[Slot]:
    start, end = period(today)
    async with session.get(URL, params={"bzn": zone, "start": start, "end": end}, timeout=30) as r:
        r.raise_for_status()
        return parse(await r.json(content_type=None))
