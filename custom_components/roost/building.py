"""The house from the Dutch building register (BAG, through PDOK), optional. Pure Python.

With the user's consent Roost asks PDOK (Kadaster) once for the buildings around the home location of Home Assistant
and keeps only three things — no address:
- the construction year and the floor area of the dwelling (verblijfsobject) nearest to the home location: starting
  values for the house model (heat loss and heat storage per m², by age), so a new install does not start from a
  generic house;
- the outline of its building (pand): the directions of the outside walls. Walls shared with a neighbour (a terraced
  house) have no windows; the sun on the facades (model.learn) is only tried for directions that have an outside wall.
The data of the house takes over within days; this only gives a better start.
"""
from __future__ import annotations

import math

WFS = ("https://service.pdok.nl/lv/bag/wfs/v2_0?service=WFS&version=2.0.0&request=GetFeature&typeNames=bag:{kind}"
       "&outputFormat=application/json&srsName=EPSG:4326&count=50&bbox={s},{w},{n},{e},urn:ogc:def:crs:EPSG::4326")
RADIUS_M = 40.0
SHARED_M = 0.6             # a wall within this distance of a neighbour's wall is shared
FACADE_REACH = 45.0        # an outside wall counts for the directions within this (south + east walls: south-east too)
# heat loss per m² of floor (W/K, walls + windows + roof + ventilation) by construction year: rough Dutch typology;
# a renovated house is better, the data corrects it
LOSS_BY_YEAR = ((1946, 3.0), (1965, 2.6), (1975, 2.2), (1992, 1.7), (2006, 1.35), (2015, 1.1), (9999, 0.85))
STORAGE_PER_M2 = 0.13      # kWh/K per m² of floor (a stone house with floor heating)
MAX_DIST_M = 25.0          # the home location must be in the building or this close to the dwelling (a rough or shifted
                           # pin would otherwise give the neighbours' house)
MAX_DWELLINGS = 2          # a building with more dwellings (flats): its outside walls say little about one home's windows


def bbox(lat: float, lon: float, radius: float = RADIUS_M) -> dict:
    dlat = radius / 111_320
    dlon = radius / (111_320 * math.cos(math.radians(lat)))
    return {"s": lat - dlat, "w": lon - dlon, "n": lat + dlat, "e": lon + dlon}


def _xy(lat0: float, lon0: float, lon: float, lat: float) -> tuple[float, float]:
    """Metres east and north of (lat0, lon0)."""
    return (lon - lon0) * 111_320 * math.cos(math.radians(lat0)), (lat - lat0) * 111_320


def _rings(geom: dict) -> list[list]:
    if geom.get("type") == "Polygon":
        return [geom["coordinates"][0]]
    if geom.get("type") == "MultiPolygon":
        return [p[0] for p in geom["coordinates"]]
    return []


def _seg_dist(p, a, b) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def outside_walls(own: list, others: list[list], lat0: float, lon0: float) -> list[tuple[float, float]]:
    """(azimuth of the outward normal in degrees from north, length in m) of each wall not shared with a neighbour."""
    pts = [_xy(lat0, lon0, x, y) for x, y in own]
    if len(pts) < 4:
        return []
    area2 = sum(pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1] for i in range(len(pts) - 1))
    ccw = area2 > 0
    nb = [[_xy(lat0, lon0, x, y) for x, y in ring] for ring in others]
    walls = []
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if length < 1.0:
            continue
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        shared = any(_seg_dist(mid, r[j], r[j + 1]) < SHARED_M for r in nb for j in range(len(r) - 1))
        if shared:
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        nx, ny = (dy, -dx) if ccw else (-dy, dx)           # outward normal
        az = (math.degrees(math.atan2(nx, ny)) + 360) % 360
        walls.append((round(az, 1), round(length, 1)))
    return walls


def parse(pand_json: dict, vbo_json: dict, lat: float, lon: float) -> dict | None:
    """From the WFS answers around the home location: {"year", "area_m2", "walls": [(azimuth, m)]} or None."""
    homes = [f for f in (vbo_json or {}).get("features", []) if "woonfunctie" in str(f.get("properties", {}).get("gebruiksdoel", ""))]
    if not homes:
        return None

    def dist(f):
        x, y = _xy(lat, lon, *f["geometry"]["coordinates"][:2])
        return math.hypot(x, y)
    home = min(homes, key=dist)
    p = home["properties"]
    pid = p.get("pandidentificatie")
    pands = (pand_json or {}).get("features", [])
    own = next((f for f in pands if f.get("properties", {}).get("identificatie") == pid), None)
    inside = own is not None and any(_inside((0.0, 0.0), [_xy(lat, lon, x, y) for x, y in r]) for r in _rings(own["geometry"]))
    if not inside and dist(home) > MAX_DIST_M:
        return None
    dwellings = int((own or {}).get("properties", {}).get("aantal_verblijfsobjecten") or 1)
    walls = []
    if own and dwellings <= MAX_DWELLINGS:
        rings = _rings(own["geometry"])
        others = [r for f in pands if f is not own for r in _rings(f["geometry"])]
        for ring in rings:
            walls += outside_walls(ring, others, lat, lon)
    year = p.get("bouwjaar") or (own or {}).get("properties", {}).get("bouwjaar")
    return {"year": int(year) if year else None, "area_m2": float(p["oppervlakte"]) if p.get("oppervlakte") else None, "walls": walls,
            "dwellings": dwellings}


def _inside(pt, poly) -> bool:
    x, y = pt
    n, hit = len(poly), False
    for i in range(n - 1):
        (x1, y1), (x2, y2) = poly[i], poly[i + 1]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def prior(b: dict | None) -> dict | None:
    """Starting values for the house model: heat loss and storage from floor area and age."""
    if not b or not b.get("area_m2") or not b.get("year"):
        return None
    area = max(30.0, min(400.0, b["area_m2"]))
    per = next(v for y, v in LOSS_BY_YEAR if b["year"] < y)
    return {"H": round(area * per / 1000, 3), "C": round(area * STORAGE_PER_M2, 1)}


def facades(b: dict | None, candidates: tuple[float, ...]) -> tuple[float, ...] | None:
    """The facade directions to try: those within FACADE_REACH of outside walls of some length (None: try all). A
    direction between two outside walls stands for windows on both (the author's house: south + east -> south-east)."""
    if not b or not b.get("walls"):
        return None
    out = []
    for c in candidates:
        L = sum(m for az, m in b["walls"] if abs((az - c + 180) % 360 - 180) <= FACADE_REACH)
        if L >= 2.0:
            out.append(c)
    return tuple(out)
