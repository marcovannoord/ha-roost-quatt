"""Heat pump model: COP, outdoor-sensor bias and maximum heat output, learned from hourly history. Pure Python.

COP = alpha + beta * T_sensor + gamma * max(0, Q - Q_REF)
    T_sensor  the heat pump's own outdoor reading (the COP curve belongs to it; it reads high in the sun, so for
              planning Roost uses the weather forecast plus the learned bias)
    Q         heat output that hour (kWh); above Q_REF the water gets hotter and the COP drops

Starting values per Quatt setup (one outdoor unit, or a Duo with two in series), from Quatt's published figures; a
few hundred hours of the user's own data take over (ridge pull towards the start values, weight ~200 hours).

The model also holds how the unit responds to the thermostat and when it makes hot water (learned in response.py).
An OpenTherm thermostat modulates: the heat asked for is about the house's loss plus a gain per degree the thermostat's
own reading is below the setpoint, and the unit follows that demand with a delay:
    demand = a · loss + k · (setpoint + offset − thermostat reading),  thermostat reading = room + th_diff
    output moves towards the demand by `follow` of the gap per hour (1 = at once); when the thermostat asks for
    nothing at all (demand ≤ 0) the unit stops at once (`stops`: seen on a Lyric T6 + Blackbird P80, and 5 % closer
    to a year of its hourly heat than a slow fall; a slow fall made the planner count on heat that never came, so it
    lowered the setpoint each time the unit ran and the unit ran in short bursts)
    q_min         lowest steady heat output; below it the unit cycles, at cyc × the COP
    dhw           share of each hour of the week (Monday 00:00 first, local time) spent on hot water: no space heating
Without learned values (k None) it is a thermostat that closes a gap within the hour: k = C per hour, no delay.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

Q_REF = 3.5
COP_MIN, COP_MAX = 1.6, 7.5

# per model family: COP start values and the maximum heat output line (kW) = a + b * T_out, clamped
PROFILES = {
    "p80": {"alpha": 3.04, "beta": 0.19, "gamma": -0.27, "pmax_a": 5.7, "pmax_b": 0.15, "pmax_lo": 5.3, "pmax_hi": 7.0},
    "p60": {"alpha": 3.04, "beta": 0.19, "gamma": -0.35, "pmax_a": 4.3, "pmax_b": 0.11, "pmax_lo": 4.0, "pmax_hi": 5.3},
    "generic": {"alpha": 3.0, "beta": 0.18, "gamma": -0.3, "pmax_a": 4.5, "pmax_b": 0.12, "pmax_lo": 3.5, "pmax_hi": 7.0},
    # Quatt (R290): one outdoor unit, and a Duo (two units in series; the COP drops less at high output because each unit
    # runs at part load). The maximum output starts low on purpose: learning only ever raises it, from whole hours the
    # unit gave more (a Duo measured 6.4-6.7 kW at -4..4 °C; a single unit about half)
    "quatt": {"alpha": 3.2, "beta": 0.17, "gamma": -0.3, "pmax_a": 3.0, "pmax_b": 0.03, "pmax_lo": 2.6, "pmax_hi": 4.5},
    "quatt_duo": {"alpha": 3.2, "beta": 0.17, "gamma": -0.15, "pmax_a": 5.8, "pmax_b": 0.05, "pmax_lo": 5.3, "pmax_hi": 8.0},
}

# maximum output lines of earlier starting profiles that were too high and could never come down (raise-only learning):
# a model still on one of them starts again from the profile above
OLD_PMAX = {"quatt": (4.6, 0.1, 3.5, 5.5), "quatt_duo": (9.2, 0.2, 7.0, 11.0)}


PMAX_KEYS = ("pmax_a", "pmax_b", "pmax_lo", "pmax_hi")


def reset_old_pmax(m: "HeatPumpModel", profile: str) -> bool:
    """The model's maximum output is still an outdated starting line: take the current profile's. True when changed."""
    old = OLD_PMAX.get(profile)
    if old is None or tuple(getattr(m, k) for k in PMAX_KEYS) != old:
        return False
    for k in PMAX_KEYS:
        setattr(m, k, PROFILES[profile][k])
    return True


# radiators need warmer water than a floor: a lower COP to start from (the unit's own meters take over)
EMITTER_COP = {"floor": 0.0, "radiators": -0.7, "both": -0.35}


def profile_for(model_name: str | None) -> str:
    n = (model_name or "").lower()
    if "quatt" in n:
        return "quatt_duo" if "duo" in n else "quatt"
    if "p80" in n:
        return "p80"
    if "p60" in n:
        return "p60"
    return "generic"


@dataclass
class HeatPumpModel:
    alpha: float = PROFILES["p80"]["alpha"]
    beta: float = PROFILES["p80"]["beta"]
    gamma: float = PROFILES["p80"]["gamma"]
    pmax_a: float = PROFILES["p80"]["pmax_a"]
    pmax_b: float = PROFILES["p80"]["pmax_b"]
    pmax_lo: float = PROFILES["p80"]["pmax_lo"]
    pmax_hi: float = PROFILES["p80"]["pmax_hi"]
    bias: float = 1.0                  # heat pump outdoor sensor minus weather service, at night (°C)
    hours: int = 0                     # heating hours behind the COP fit
    source: str = "profile"
    # response to the thermostat (learned in response.py)
    a: float = 1.0                     # share of the house's loss the demand follows
    k: float | None = None             # kW per °C below the setpoint; None: the house's C per hour (closes a gap in an hour)
    offset: float = 0.0                # the unit heats towards setpoint + offset (°C, in the thermostat's reading)
    follow: float = 1.0                # share of the gap between output and demand closed per hour
    stops: bool = True                 # no demand at all: the output stops at once (False: it falls with `follow`)
    th_diff: float = 0.0               # thermostat reading minus the room sensor (°C)
    q_min: float = 0.0                 # lowest steady heat output (kW); 0 = unknown
    cyc: float = 1.0                   # COP factor while cycling below q_min
    resp_hours: int = 0
    resp_error: float | None = None    # kWh per hour over 6 hours, heat output predicted against measured
    resp_source: str = "default"
    dhw: list[float] | None = None     # 168 values: share of the hour on hot water, Monday 00:00 first (local time)
    dhw_weeks: float = 0.0

    @classmethod
    def for_profile(cls, name: str) -> "HeatPumpModel":
        p = PROFILES.get(name, PROFILES["generic"])
        return cls(**p, source=f"profile {name}")

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None, profile: str = "p80") -> "HeatPumpModel":
        m = cls.for_profile(profile)
        for k, v in (d or {}).items():
            if hasattr(m, k):
                setattr(m, k, v)
        return m

    def cop(self, t_out: float, q_kw: float) -> float:
        """COP at the weather service's outdoor temperature (bias added) and a heat output in kW."""
        c = self.alpha + self.beta * (t_out + self.bias) + self.gamma * max(0.0, q_kw - Q_REF)
        return max(COP_MIN, min(COP_MAX, c))

    def pmax(self, t_out: float) -> float:
        return max(self.pmax_lo, min(self.pmax_hi, self.pmax_a + self.pmax_b * t_out))

    def demand(self, loss_net: float, sp: float, room: float, C: float) -> float:
        """Heat the thermostat asks for (kW, not clamped): loss_net = loss − sun − other gains."""
        k = self.k if self.k is not None else C
        return self.a * loss_net + k * (sp + self.offset - room - self.th_diff)

    def dhw_share(self, weekday: int, hour: int) -> float:
        """Expected share of this local hour spent on hot water (weekday 0 = Monday)."""
        if not self.dhw or len(self.dhw) != 168:
            return 0.0
        return self.dhw[(weekday % 7) * 24 + hour % 24]


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


def learn(rows, previous: HeatPumpModel, prior_hours: float = 200.0) -> tuple[HeatPumpModel, str]:
    """rows: model.HourRow. Uses hours with ≥ 0.3 kWh electricity for heating and almost no hot water."""
    m = HeatPumpModel.from_dict(previous.as_dict())
    use = [r for r in rows if r.E >= 0.3 and r.dhw_s < 600 and r.T_out_sensor is not None and r.Q > 0 and 1.0 <= r.Q / r.E <= 8.0]
    notes = []
    if len(use) >= 30:
        theta0 = [m.alpha, m.beta, m.gamma]
        X = [[1.0, r.T_out_sensor, max(0.0, r.Q - Q_REF)] for r in use]
        y = [r.Q / r.E for r in use]
        A = [[0.0] * 3 for _ in range(3)]
        b = [0.0] * 3
        for xi, yi in zip(X, y):
            for i in range(3):
                b[i] += xi[i] * yi
                for j in range(3):
                    A[i][j] += xi[i] * xi[j]
        for i in range(3):            # pull towards the start values, as if they were `prior_hours` hours
            lam = prior_hours * max(1e-6, sum(x[i] ** 2 for x in X) / len(X))
            A[i][i] += lam
            b[i] += lam * theta0[i]
        th = _solve(A, b)
        if th and 2.0 <= th[0] <= 6.0 and 0.03 <= th[1] <= 0.4 and -0.8 <= th[2] <= 0.0:
            m.alpha, m.beta, m.gamma = (round(v, 3) for v in th)
            m.hours, m.source = len(use), "learned"
            notes.append(f"COP from {len(use)} heating hours")
        else:
            notes.append("COP fit out of range: kept")
    else:
        notes.append(f"COP: {len(use)} heating hours, need 30")
    night = sorted(r.T_out_sensor - r.T_out for r in rows if r.T_out_sensor is not None and r.rad < 0.01
                   and -30 < r.T_out_sensor < 45)
    if len(night) >= 24:
        m.bias = round(max(-3.0, min(5.0, night[len(night) // 2])), 2)
        notes.append(f"outdoor sensor bias {m.bias:+.1f} °C")
    # maximum output: only ever raised above the profile, from hours the unit's history shows as fully heating at a high
    # output (whole hours at low power in mild weather say nothing about the maximum)
    pts = [(r.T_out, r.Q) for r in rows if r.heating_s >= 3300 and r.dhw_s < 60 and r.Q > m.pmax(r.T_out) * 0.97]
    if len(pts) >= 5:
        over = sorted(q - m.pmax(t) for t, q in pts)
        lift = over[int(len(over) * 0.9)]
        if lift > 0:
            m.pmax_a = round(m.pmax_a + lift, 2)
            m.pmax_hi = round(m.pmax_hi + lift, 2)
            notes.append(f"maximum output raised {lift:+.1f} kW ({len(pts)} hours above the profile)")
    return m, "; ".join(notes)
