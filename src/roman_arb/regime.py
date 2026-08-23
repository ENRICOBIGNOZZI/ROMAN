from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass
class _State:
    n: int = 0
    mean: float = 0.0
    var: float = 1e-4
    ph_up: float = 0.0
    ph_down: float = 0.0
    stress_left: int = 0
    stressed: bool = False


@dataclass(frozen=True)
class RegimeEstimate:
    stressed: bool
    z_score: float
    weight: float
    volatility: float
    n: int


class RegimeDetector:
    """EWMA + genuinely two-sided Page-Hinkley-style regime control.

    Both persistent upward and downward location shifts are detected. A detected
    regime change is held for several subsequent observations so model weights do
    not immediately jump back to normal after a single quiet print.
    """

    def __init__(
        self,
        alpha: float = 0.08,
        ph_drift: float = 0.0015,
        ph_threshold: float = 0.035,
        stress_hold_updates: int = 6,
    ):
        self.alpha = max(1e-6, min(1.0, float(alpha)))
        self.ph_drift = max(0.0, float(ph_drift))
        self.ph_threshold = max(1e-9, float(ph_threshold))
        self.stress_hold_updates = max(0, int(stress_hold_updates))
        self.states: dict[str, _State] = {}

    def update(self, key: str, value: float) -> RegimeEstimate:
        k = (key or "global").strip().lower()
        s = self.states.setdefault(k, _State())
        try:
            x = float(value)
        except Exception:
            return self.estimate(k)
        if not math.isfinite(x):
            return self.estimate(k)
        if s.n == 0:
            s.mean = x
            s.var = 1e-4
            s.n = 1
            return self.estimate(k)

        old_mean = s.mean
        old_vol = math.sqrt(max(s.var, 1e-12))
        innov = x - old_mean

        a = self.alpha
        s.mean = (1.0 - a) * s.mean + a * x
        s.var = (1.0 - a) * s.var + a * innov * innov
        s.n += 1

        # Positive and negative cumulative deviations must be tracked separately.
        # A single minimum-cumulative statistic only detects one persistent side.
        s.ph_up = max(0.0, s.ph_up + innov - self.ph_drift)
        s.ph_down = max(0.0, s.ph_down - innov - self.ph_drift)
        shock = abs(innov) > 3.0 * max(old_vol, 1e-6)
        detected = bool(
            s.ph_up > self.ph_threshold
            or s.ph_down > self.ph_threshold
            or shock
        )

        if detected:
            s.ph_up = 0.0
            s.ph_down = 0.0
            s.stress_left = self.stress_hold_updates
        elif s.stress_left > 0:
            s.stress_left -= 1
        s.stressed = bool(detected or s.stress_left > 0)
        return self.estimate(k)

    def estimate(self, key: str) -> RegimeEstimate:
        s = self.states.get((key or "global").strip().lower(), _State())
        vol = math.sqrt(max(s.var, 1e-12))
        z = s.mean / vol if vol > 0 else 0.0
        sample_conf = s.n / (s.n + 24.0)
        weight = (0.45 if s.stressed else 1.0) * (0.55 + 0.45 * sample_conf)
        return RegimeEstimate(
            stressed=s.stressed,
            z_score=max(-8.0, min(8.0, z)),
            weight=max(0.20, min(1.0, weight)),
            volatility=vol,
            n=s.n,
        )
