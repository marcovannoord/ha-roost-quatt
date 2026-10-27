"""Extra rooms the heat pump also heats (radiators upstairs, a bedroom, a study), watched by Roost. Pure Python.

The thermostat that Roost steers is in one room (often the living room with floor heating). Other rooms get heat only
while the heat pump runs for that thermostat. Each extra room has a sensor, a kind and a minimum for some hours; Roost
learns per room how it cools and warms, and the planner keeps those minimums (a penalty firmer than the comfort
temperature's, softer than the hard minimum of the main room), so it does not leave the heat pump off longer than those rooms can take. Outside its hours a room may get
as cool as it likes: a bedroom is often meant to be cool, and a radiator valve that is closed on purpose stays closed.

Room model per hour (least squares on the hours with data, coefficients not negative):
    T_room += b0 + b_heat · heat from the heat pump (kWh) + b_out · (T_out − T_room) + b_main · (T_main − T_room)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

# kind -> minimum (°C) and the local hours it holds [from, to); None: the comfort hours of the house
KINDS = {
    "bedroom": {"min": 16.0, "from": 19, "to": 23},
    "kids": {"min": 18.0, "from": 7, "to": 21},
    "study": {"min": 19.0, "from": 8, "to": 18},
    "bathroom": {"min": 20.0, "from": 6, "to": 9},
    "other": {"min": 17.0, "from": None, "to": None},
}
MIN_HOURS = 72
PENALTY = 1.0             # currency per °C·hour below the minimum: a minimum, firmer than the comfort temperature
PENALTY_FAR = 3.0         # more than a degree below
COLD_MARGIN = 0.5         # °C below the minimum that counts as too cold
COLD_HOURS = 3            # hours too cold on a day ...
COLD_DAYS = 2             # ... on this many of the last three days -> a repair


@dataclass
class Room:
    id: str
    name: str
    sensor: str
    kind: str = "other"
    minimum: float | None = None
    hour_from: int | None = None
    hour_to: int | None = None

    def settings(self, day_from: int, day_to: int) -> tuple[float, int, int]:
        """(minimum, from, to) with the kind's defaults (and the house's comfort hours for 'other')."""
        k = KINDS.get(self.kind, KINDS["other"])
        lo = self.minimum if self.minimum is not None else k["min"]
        a = self.hour_from if self.hour_from is not None else (k["from"] if k["from"] is not None else day_from)
        b = self.hour_to if self.hour_to is not None else (k["to"] if k["to"] is not None else day_to)
        return float(lo), int(a), int(b)


def active(hour: int, hour_from: int, hour_to: int) -> bool:
    """Does the minimum hold in this local hour (through midnight when from > to)?"""
    if hour < 0:
        return False
    return (hour_from <= hour < hour_to) if hour_from <= hour_to else (hour >= hour_from or hour < hour_to)


@dataclass
class RoomModel:
    b0: float = 0.0
    b_heat: float = 0.05
    b_out: float = 0.02
    b_main: float = 0.05
    error: float | None = None       # °C per hour, one hour ahead
    hours: int = 0
    source: str = "default"

    def step(self, T: float, heat: float, t_out: float, t_main: float) -> float:
        return T + self.b0 + self.b_heat * heat + self.b_out * (t_out - T) + self.b_main * (t_main - T)

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "RoomModel":
        m = cls()
        for k, v in (d or {}).items():
            if hasattr(m, k):
                setattr(m, k, v)
        return m


def _solve(A: list[list[float]], b: list[float]) -> list[float] | None:
    n = len(b)
    M = [A[i][:] + [b[i]] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-12:
            return None
        M[c], M[p] = M[p], M[c]
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                for k in range(c, n + 1):
                    M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] for i in range(n)]


def learn(samples: list[tuple[float, float, float, float, float]]) -> RoomModel | None:
    """samples: (T_room, T_room an hour later, heat kWh, T_out, T_main). Coefficients that come out negative are set
    to 0 and the rest fitted again (a room does not cool from heat or warm from the cold)."""
    if len(samples) < MIN_HOURS:
        return None
    names = ["b0", "b_heat", "b_out", "b_main"]
    free = list(names)
    coef = {n: 0.0 for n in names}
    for _ in range(4):
        X = [[{"b0": 1.0, "b_heat": q, "b_out": to - T, "b_main": tm - T}[n] for n in free] for T, _T1, q, to, tm in samples]
        y = [T1 - T for T, T1, _q, _to, _tm in samples]
        k = len(free)
        A = [[sum(x[i] * x[j] for x in X) + (1e-3 if i == j else 0.0) for j in range(k)] for i in range(k)]
        bb = [sum(x[i] * yy for x, yy in zip(X, y)) for i in range(k)]
        sol = _solve(A, bb)
        if sol is None:
            return None
        coef = {n: 0.0 for n in names}
        coef.update(dict(zip(free, sol)))
        neg = [n for n in free if n != "b0" and coef[n] < 0]
        if not neg:
            break
        free = [n for n in free if n not in neg]
    m = RoomModel(**{n: round(coef[n], 4) for n in names}, hours=len(samples), source="learned")
    se = sum((m.step(T, q, to, tm) - T1) ** 2 for T, T1, q, to, tm in samples)
    m.error = round((se / len(samples)) ** 0.5, 3)
    return m


def penalty(T: float, minimum: float) -> float:
    """Comfort cost of an hour at T in a room that should be at least `minimum`."""
    d = minimum - T
    if d <= 0:
        return 0.0
    return d * PENALTY + max(0.0, d - 1.0) * PENALTY_FAR


def too_cold(log: list[tuple[str, bool, float, float]]) -> bool:
    """log: (local date, active, T, minimum) per hour of the last days -> a lasting problem (see COLD_*)."""
    per: dict[str, int] = {}
    for date, act, T, lo in log:
        if act and T < lo - COLD_MARGIN:
            per[date] = per.get(date, 0) + 1
    dates = sorted({d for d, *_ in log})[-3:]
    return sum(1 for d in dates if per.get(d, 0) >= COLD_HOURS) >= COLD_DAYS
