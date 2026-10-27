"""A plan that holds: when Roost plans afresh and when it keeps to the plan it made. Pure Python.

Planning every quarter of an hour made the plan follow every small change in what Roost measures: the room a tenth
warmer, the unit running or not, a correction after an hour. Each new plan was a little different, so the thermostat
went up and down and the heat pump ran in short bursts. Prices do not change once published, so a plan only needs
to change when something real does. Between those moments Roost keeps the setpoints it chose and only works out
again what they will give (the expected room and cost, from what it measures now).

Roost plans afresh when:
- there is no plan yet, or the plan it holds runs out or is older than MAX_AGE_H;
- new prices are published (tomorrow's day-ahead prices), or a price in the plan changed;
- the room is clearly warmer or colder than the plan expected (ROOM_K, coarser for a thermostat in half degrees);
- the weather forecast for the coming hours changed clearly (outdoor temperature or sun on the house);
- own solar is clearly more or less than the plan counted on (the forecast changed, or the panels give clearly more
  or less now than forecast for this hour);
- the user changed something (settings, away, mode), the window closed, learning made new models (`force`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

MAX_AGE_H = 6           # a plan is made afresh at least this often (simulations: 12 h let comfort slip in fast houses)
ROOM_K = 0.25           # the room this far from what the plan expected now (°C; 0.4 in the simulations: +47 % below comfort) ...
ROOM_K_COARSE = 0.6     # ... with a thermostat that reads in half degrees
ROOM_TICKS = 2          # ... on this many checks in a row (one reading is not enough)
WEATHER_H = 6           # the coming hours compared
T_OUT_K = 1.5           # mean outdoor temperature difference over them (°C)
RAD_KW = 0.12           # mean difference of the sun on the house over them (kW/m²)
PV_KWH = 1.5            # own solar forecast over the coming WEATHER_H hours (kWh)
PV_NOW_KW = 1.5         # the panels now (mean over PV_MIN) against the forecast for this hour (kW)
PV_MIN = 15
PRICE_EPS = 0.01        # currency per kWh: a price in the plan that changed
NEW_PRICES_H = 2        # published prices reach this many hours further than the plan: new prices ...
HORIZON_H = 36          # ... when the plan was cut short by the prices published (a full horizon just moves on)


@dataclass
class Commitment:
    """What a plan made afresh chose and expected. Hours count from `hour0` (the start of the hour it was made in)."""
    at: float                                   # when it was made (epoch s)
    hour0: int                                  # start of that hour (epoch s)
    sp: list[float]                             # the setpoint per hour
    room0: float                                # the room when it was made
    t_end: list[float]                          # the room expected at the end of each hour
    t_out: list[float]                          # the outdoor temperature it planned with, per hour
    rad: list[float]                            # the sun on the house it planned with, per hour
    tariff: list[float]                         # the import price per hour it planned with
    pv: list[float] | None = None               # the own solar forecast it planned with (kWh per hour)
    fallback: str | None = None                 # made without prices ("no_price"): any real price replaces it

    def as_dict(self) -> dict:
        return dict(vars(self))

    @classmethod
    def from_dict(cls, d: dict | None) -> "Commitment | None":
        if not d:
            return None
        try:
            return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})
        except TypeError:
            return None

    def offset(self, now: float) -> int:
        return int(now // 3600) - int(self.hour0 // 3600)

    def setpoints(self, now: float) -> list[float]:
        """The setpoints still ahead, from the current hour."""
        i = self.offset(now)
        return self.sp[i:] if i >= 0 else []

    def expected_room(self, now: float) -> float | None:
        """The room the plan expected now: between the start and end of the current hour."""
        i = self.offset(now)
        if i < 0 or i >= len(self.t_end):
            return None
        end = self.hour0 + (i + 1) * 3600
        start_ts, start_t = (self.at, self.room0) if i == 0 else (end - 3600, self.t_end[i - 1])
        span = end - start_ts
        f = 1.0 if span <= 0 else min(1.0, max(0.0, (now - start_ts) / span))
        return start_t + f * (self.t_end[i] - start_t)


@dataclass
class Watch:
    """What the checks remember between ticks."""
    room_off: int = 0                           # checks in a row with the room off the plan
    pv: list = field(default_factory=list)      # (t, kW from the panels) over the last PV_MIN

    def feed_pv(self, t: float, kw: float | None) -> float | None:
        """The panels' mean power over the last PV_MIN minutes, None until that much is seen."""
        if kw is not None:
            self.pv.append((t, kw))
        self.pv = [(a, v) for a, v in self.pv if t - a <= PV_MIN * 60]
        if not self.pv or t - self.pv[0][0] < (PV_MIN - 3) * 60:
            return None
        return sum(v for _, v in self.pv) / len(self.pv)


def _mean_abs(a: list[float], b: list[float]) -> float | None:
    n = min(len(a), len(b))
    if not n:
        return None
    return sum(abs(x - y) for x, y in zip(a[:n], b[:n])) / n


def why_plan(c: Commitment | None, now: float, *, room: float | None, coarse: bool, tariff: list[float] | None,
             t_out: list[float] | None, rad: list[float] | None, pv: list[float] | None, pv_now_kw: float | None,
             watch: Watch, force: str | None = None) -> str | None:
    """-> the reason to plan afresh now, or None: keep to the plan held. The lists start at the current hour."""
    if force:
        return force
    if c is None:
        return "first"
    i = c.offset(now)
    if i < 0 or i >= len(c.sp):
        return "horizon"
    if now - c.at >= MAX_AGE_H * 3600:
        return "age"
    if c.fallback and tariff:
        return "prices"
    if tariff:
        mine = c.tariff[i:]
        if len(c.tariff) < HORIZON_H and len(tariff) >= len(mine) + NEW_PRICES_H:
            return "prices"
        if any(abs(a - b) > PRICE_EPS for a, b in zip(mine, tariff)):
            return "prices"
    exp = c.expected_room(now)
    if room is not None and exp is not None and abs(room - exp) > (ROOM_K_COARSE if coarse else ROOM_K):
        watch.room_off += 1
        if watch.room_off >= ROOM_TICKS:
            return "room"
    else:
        watch.room_off = 0
    if t_out:
        d = _mean_abs(c.t_out[i:i + WEATHER_H], t_out[:WEATHER_H])
        if d is not None and d > T_OUT_K:
            return "weather"
    if rad:
        d = _mean_abs(c.rad[i:i + WEATHER_H], rad[:WEATHER_H])
        if d is not None and d > RAD_KW:
            return "sun"
    if pv is not None and c.pv is not None:
        n = min(WEATHER_H, len(pv), len(c.pv) - i)
        if n > 0 and abs(sum(pv[:n]) - sum(c.pv[i:i + n])) > PV_KWH:
            return "solar"
    if pv_now_kw is not None and c.pv is not None and i < len(c.pv):
        if abs(pv_now_kw - c.pv[i]) > PV_NOW_KW:
            return "solar"
    return None
