"""The sun's position and the sun on a facade. Pure Python.

Windows face a direction: a south-east window gets the low winter sun in the morning, a west window the summer
evening. With the direct and diffuse radiation of the weather service (kW/m² on the horizontal), the sun on a vertical
facade facing `azimuth` (degrees from north, clockwise: 90 east, 180 south, 270 west) is
    direct normal × cos(angle of incidence) + half the diffuse sky + a little reflected from the ground.
The house model learns which direction (and how much vertical against horizontal: roof windows, glass roofs) fits the
house best (model.learn). Without direct/diffuse data the global radiation is used as it is.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

GROUND = 0.2            # albedo
FACADES = (90.0, 135.0, 180.0, 225.0, 270.0)


def position(ts: float, lat: float, lon: float) -> tuple[float, float]:
    """(elevation, azimuth) in degrees at epoch ts; azimuth from north, clockwise (NOAA approximation)."""
    d = datetime.fromtimestamp(ts, timezone.utc)
    g = 2 * math.pi / 365 * (d.timetuple().tm_yday - 1 + (d.hour + d.minute / 60 - 12) / 24)
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    eot = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g) - 0.014615 * math.cos(2 * g)
                    - 0.040849 * math.sin(2 * g))
    ha = math.radians((d.hour * 60 + d.minute + d.second / 60 + eot + 4 * lon) / 4 - 180)
    phi = math.radians(lat)
    cz = math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.cos(ha)
    el = 90 - math.degrees(math.acos(max(-1.0, min(1.0, cz))))
    az = math.degrees(math.atan2(math.sin(ha), math.cos(ha) * math.sin(phi) - math.tan(decl) * math.cos(phi))) + 180
    return el, az % 360


def effective(ts: float, wx: tuple, lat: float, lon: float, facade: float, vertical: float) -> float:
    """Radiation that drives the solar gain in the hour starting at ts (kW/m²): (1 − vertical) × global +
    vertical × the sun on a facade facing `facade`. wx: (t_out, global, wind[, direct, diffuse])."""
    ghi = wx[1] or 0.0
    if vertical <= 0 or len(wx) < 5 or wx[3] is None or ghi <= 0:
        return ghi
    el, az = position(ts + 1800, lat, lon)
    dni = min(1.0, wx[3] / math.sin(math.radians(el))) if el > 3 else 0.0
    cos_i = math.cos(math.radians(el)) * math.cos(math.radians(az - facade))
    vert = dni * max(0.0, cos_i) + wx[4] * 0.5 + ghi * GROUND * 0.5
    return (1 - vertical) * ghi + vertical * vert
