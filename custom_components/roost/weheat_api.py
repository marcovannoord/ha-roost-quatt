"""Read-only access to a Weheat heat pump's history, with Roost's own Weheat login.

The login is made in Roost's setup (or its reauth): the user logs in with the Weheat account on Weheat's page, through
the app registration the Weheat integration already has in Home Assistant. Roost keeps the token in its config entry
and refreshes it with Home Assistant's OAuth helper; when that is refused, Home Assistant asks the user to log in again.
Endpoints are the Weheat third-party API (hourly logs and energy logs; the installation settings for the heating curve). The first import fetches the history a month
per call and Roost keeps it; after that only the last hours, once a night. Weheat's limits (logs at most every 2
minutes, energy logs at most every half hour) are kept."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from aiohttp import ClientResponseError

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.config_entry_oauth2_flow import (
    AbstractOAuth2Implementation, OAuth2Session, async_get_config_entry_implementation, async_get_implementations,
)

_LOGGER = logging.getLogger(__name__)
API_URL = "https://api.weheat.nl/third_party"


class WeheatUnavailable(Exception):
    """No usable Weheat login right now (try again later)."""


class WeheatLoginNeeded(WeheatUnavailable):
    """No Weheat login, or Weheat refused it: the user has to log in (reauth)."""


def heat_pump_id(hass: HomeAssistant, device_id: str) -> tuple[str | None, str | None]:
    """(Weheat heat pump id, config entry id of the Weheat integration) for a device."""
    dev = dr.async_get(hass).async_get(device_id)
    if dev is None:
        return None, None
    hp = next((i[1] for i in dev.identifiers if i[0] == "weheat"), None)
    # HA 2026.10+ has one config entry per device (config_entry_id); older versions only a set (config_entries).
    ids = [dev.config_entry_id] if getattr(dev, "config_entry_id", None) else list(dev.config_entries)
    entry = next((e for e in ids if (ce := hass.config_entries.async_get_entry(e)) and ce.domain == "weheat"), None)
    return hp, entry


async def _access(hass: HomeAssistant, entry_id: str) -> str:
    """The access token of Roost's own Weheat login (entry_id: Roost's entry), refreshed when needed."""
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or not entry.data.get("token"):
        raise WeheatLoginNeeded("not logged in to Weheat yet")
    try:
        if entry.data.get("auth_from") == "weheat":       # logged in with the Weheat integration's app registration
            impl = (await async_get_implementations(hass, "weheat")).get(entry.data.get("auth_implementation"))
            if impl is None:
                raise WeheatLoginNeeded("the Weheat integration's app registration is gone")
        else:
            impl = await async_get_config_entry_implementation(hass, entry)
        session = OAuth2Session(hass, entry, impl)
        await session.async_ensure_token_valid()          # refreshes when needed and keeps it in the entry
        return session.token["access_token"]
    except WeheatUnavailable:
        raise
    except ClientResponseError as err:
        if err.status in (400, 401, 403):                 # the refresh was refused: log in again
            raise WeheatLoginNeeded(f"Weheat refused the login ({err.status})") from err
        raise WeheatUnavailable(f"Weheat's login server: {err.status}") from err
    except Exception as err:  # noqa: BLE001 - Weheat's login server unreachable, provider unavailable
        raise WeheatUnavailable(f"Weheat login: {err}") from err


async def weheat_implementation(hass: HomeAssistant) -> AbstractOAuth2Implementation | None:
    """The app registration (Client ID and Secret) the user gave the Weheat integration, so Roost's own login is just
    'log in with your Weheat account'. The one the Weheat integration's entry uses first."""
    try:
        impls = await async_get_implementations(hass, "weheat")
    except Exception:  # noqa: BLE001 - not set up, or its provider unavailable
        return None
    used = [e.data.get("auth_implementation") for e in hass.config_entries.async_entries("weheat")]
    return next((impls[k] for k in used if k in impls), None) or next(iter(impls.values()), None)


async def _get(hass: HomeAssistant, entry_id: str, path: str, params: dict) -> list[dict]:
    for attempt in range(4):
        try:
            token = await _access(hass, entry_id)
        except WeheatLoginNeeded:
            raise
        except WeheatUnavailable:
            if attempt == 3:
                raise
            await asyncio.sleep(40)             # Weheat's login server did not answer: a little later
            continue
        async with async_get_clientsession(hass).get(f"{API_URL}{path}", params=params, timeout=60,
                                                     headers={"Authorization": f"Bearer {token}"}) as r:
            if r.status == 401:
                raise WeheatLoginNeeded("Weheat refused the token (401)")
            r.raise_for_status()
            data = await r.json()
            return data if isinstance(data, list) else []
    return []


def _fmt(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _when(row: dict) -> datetime | None:
    v = row.get("timeBucket")
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


CONTROL_METHODS = {1: "heating_curve", 2: "on_off", 3: "opentherm", 4: "opentherm_smart", 5: "cloud_thermostat"}


async def async_settings(hass: HomeAssistant, entry_id: str, pump_id: str) -> dict | None:
    """The installation's settings (read-only): how the unit is controlled and its heating curve. The heat pump does
    not carry its installation: the list of installations does. {"available": False, ...} when Weheat does not give
    them to this login (the advice then shows what the unit made instead of the curve it has); None on an error."""
    try:
        token = await _access(hass, entry_id)
        session, auth = async_get_clientsession(hass), {"Authorization": f"Bearer {token}"}
        async with session.get(f"{API_URL}/api/v1/installations", timeout=30, headers=auth) as r:
            if r.status != 200:
                return {"available": False, "status": r.status}
            listed = await r.json()
        items = listed.get("data", []) if isinstance(listed, dict) else listed if isinstance(listed, list) else []
        inst = next((x.get("id") for x in items if isinstance(x, dict) and x.get("heatPumpId") == pump_id), None)
        if not inst:
            return {"available": False, "status": "no installation for this heat pump"}
        async with session.get(f"{API_URL}/api/v1/installations/{inst}/settings", timeout=30, headers=auth) as r:
            if r.status != 200:
                return {"available": False, "status": r.status}
            data = await r.json()
    except Exception as err:  # noqa: BLE001 - an extra: never in the way of the rest
        _LOGGER.debug("Roost: Weheat settings not available: %s", err)
        return None
    if not isinstance(data, dict):
        return {"available": False, "status": "no object"}
    xs, ys = data.get("heatingCurveX"), data.get("heatingCurveY")
    curve = ([[float(x), float(y)] for x, y in zip(xs, ys)]
             if isinstance(xs, list) and isinstance(ys, list) and len(xs) == len(ys) and xs else None)
    return {"available": True, "control": CONTROL_METHODS.get(data.get("controlMethod"), data.get("controlMethod")),
            "curve": curve}


async def async_pump_info(hass: HomeAssistant, entry_id: str, pump_id: str) -> dict | None:
    """The heat pump's fixed data from Weheat: model (0 Blackbird P80, 1 Blackbird P60, 2-4 Sparrow P60, 5 Flint P40),
    boiler_type (0 unknown, 1 none, 2 on/off, 3 OpenTherm), dhw_type (1 hot water tank, 2 none), commissioned (ISO).
    None on an error."""
    try:
        async with async_get_clientsession(hass).get(f"{API_URL}/api/v1/heat-pumps/{pump_id}", timeout=30,
                                                     headers={"Authorization": f"Bearer {await _access(hass, entry_id)}"}) as r:
            r.raise_for_status()
            data = await r.json()
    except Exception as err:  # noqa: BLE001 - an extra: never in the way of the rest
        _LOGGER.debug("Roost: Weheat heat pump data not available: %s", err)
        return None
    if not isinstance(data, dict):
        return None

    def num(k: str) -> int | None:
        v = data.get(k)
        return v if isinstance(v, int) and not isinstance(v, bool) else None
    return {"model": num("model"), "boiler_type": num("boilerType"), "dhw_type": num("dhwType"),
            "commissioned": data.get("commissionedAt") if isinstance(data.get("commissionedAt"), str) else None}


async def async_commissioned(hass: HomeAssistant, entry_id: str, pump_id: str) -> datetime | None:
    """When the heat pump was put into use: no history before it, so no need to ask for it."""
    info = await async_pump_info(hass, entry_id, pump_id)
    when = _when({"timeBucket": info.get("commissioned")}) if info else None
    return when - timedelta(days=1) if when else None


class Pacer:
    """Weheat's limits for developers: heat pump logs at most once every 2 minutes, energy logs at most once every
    half hour. Only applies between calls of the same kind. `last` (unix time of the last call per kind) is the
    caller's, kept across restarts, so an import that carries on after a restart still keeps the limits."""

    GAP = {"logs": 120.0, "energy": 1800.0}

    def __init__(self, last: dict[str, float] | None = None) -> None:
        self.last: dict[str, float] = last if last is not None else {}
        self.calls = 0

    async def wait(self, kind: str) -> None:
        if kind in self.last:
            rest = min(self.GAP[kind], self.GAP[kind] - (time.time() - self.last[kind]))   # a clock set back waits no longer than a gap
            if rest > 0:
                await asyncio.sleep(rest)
        self.last[kind] = time.time()
        self.calls += 1


MONTH = timedelta(days=31)       # the API refuses longer periods (tried: 45 days refused, 23 accepted)


async def _get_window(hass: HomeAssistant, entry_id: str, path: str, kind: str, t: datetime, t2: datetime, pacer: Pacer,
                      note=None) -> list[dict] | None:
    """One period; None when the API refuses it (too long)."""
    await pacer.wait(kind)
    try:
        rows = await _get(hass, entry_id, path, {"startTime": _fmt(t), "endTime": _fmt(t2), "interval": "Hour"})
    except ClientResponseError as err:
        if note:
            note(endpoint=kind, start=_fmt(t), end=_fmt(t2), status=err.status)
        if err.status in (400, 413, 414, 422):
            return None
        raise
    if note:
        last = max((w for w in map(_when, rows) if w), default=None)
        note(endpoint=kind, start=_fmt(t), end=_fmt(t2), rows=len(rows), last=_fmt(last) if last else None)
    return rows


async def async_fetch_months(hass: HomeAssistant, entry_id: str, pump_id: str, start: datetime, end: datetime,
                             on_month, note=None, last_calls: dict | None = None, energy_logs: bool = True) -> int:
    """The history between start and end, newest month first, within Weheat's limits (logs at most every 2 minutes,
    energy logs at most every half hour: a year takes some hours, in the background; logs alone, to add fields to
    hours Roost already has, about half an hour). After each month on_month(logs, energy, oldest datetime done) is
    awaited, so Roost can keep and learn from what came in. -> number of calls."""
    first = await async_commissioned(hass, entry_id, pump_id) if end - start > timedelta(days=31) else None
    if first and first > start:
        start = first
    pacer = Pacer(last_calls)
    span = MONTH
    t2 = end
    while t2 > start:
        t = max(start, t2 - span)
        logs = await _get_window(hass, entry_id, f"/api/v1/heat-pumps/{pump_id}/logs", "logs", t, t2, pacer, note)
        if logs is None:
            if span <= timedelta(days=2):
                raise RuntimeError("the Weheat API refuses even short periods")
            span = span / 2
            continue
        energy = await _get_window(hass, entry_id, f"/api/v1/energy-logs/{pump_id}", "energy", t, t2, pacer, note) \
            if energy_logs else []
        if energy is None:                      # energy logs may allow less: same period in halves
            energy = []
            mid = t + (t2 - t) / 2
            for a, b in ((t, mid), (mid, t2)):
                energy += await _get_window(hass, entry_id, f"/api/v1/energy-logs/{pump_id}", "energy", a, b, pacer, note) or []
        await on_month(logs, energy, t)
        t2 = t
    return pacer.calls + (1 if first else 0)


async def _fetch(hass: HomeAssistant, entry_id: str, path: str, kind: str, start: datetime, end: datetime,
                 pacer: Pacer, progress=None, note=None) -> list[dict]:
    """Everything between start and end in as few calls as possible: first the whole period at once; when the API
    sends less than asked (a cap on the number of rows) carry on from the last hour it sent; when it refuses a period
    that long, halve it."""
    out: list[dict] = []
    t, span = start, end - start
    while t < end:
        t2 = min(end, t + span)
        await pacer.wait(kind)
        try:
            rows = await _get(hass, entry_id, path, {"startTime": _fmt(t), "endTime": _fmt(t2), "interval": "Hour"})
        except ClientResponseError as err:
            if note:
                note(endpoint=kind, start=_fmt(t), end=_fmt(t2), status=err.status)
            if err.status in (400, 413, 414, 422, 500, 502, 504) and span > timedelta(days=2):
                span = span / 2
                continue
            raise
        out += rows
        last = max((w for w in map(_when, rows) if w), default=None)
        if note:
            note(endpoint=kind, start=_fmt(t), end=_fmt(t2), rows=len(rows), last=_fmt(last) if last else None)
        if rows and last and last < t2 - timedelta(hours=2) and len(rows) >= 100:
            t = last + timedelta(hours=1)        # cut off: continue after the last hour that came
        else:
            t = t2
        if progress:
            progress(t)
    return out


async def async_fetch_history(hass: HomeAssistant, entry_id: str, pump_id: str, start: datetime, end: datetime,
                              progress=None, note=None, last_calls: dict | None = None) -> tuple[list[dict], list[dict], int]:
    """Hourly logs and hourly energy logs between start and end (from the commissioning date at the earliest), within
    Weheat's limits. -> (logs, energy, number of calls)."""
    first = await async_commissioned(hass, entry_id, pump_id) if end - start > timedelta(days=31) else None
    if first and first > start:
        start = first
    pacer = Pacer(last_calls)
    logs = await _fetch(hass, entry_id, f"/api/v1/heat-pumps/{pump_id}/logs", "logs", start, end, pacer, progress, note)
    energy = await _fetch(hass, entry_id, f"/api/v1/energy-logs/{pump_id}", "energy", start, end, pacer, progress, note)
    return logs, energy, pacer.calls + (1 if first else 0)
