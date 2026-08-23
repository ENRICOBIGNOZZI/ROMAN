from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass
class _State:
    n: int = 0
    mean: float = 0.0
    var: float = 1e-4
    ph: float = 0.0
    min_ph: float = 0.0
    stressed: bool = False


@dataclass(frozen=True)
class RegimeEstimate:
    stressed: bool
    z_score: float
    weight: float
    volatility: float
    n: int


class RegimeDetector:
    """EWMA + Page-Hinkley style detector for simple online regime control."""

    def __init__(self, alpha: float = 0.08, ph_drift: float = 0.0015, ph_threshold: float = 0.035):
        self.alpha = float(alpha)
        self.ph_drift = float(ph_drift)
        self.ph_threshold = float(ph_threshold)
        self.states: dict[str, _State] = {}

    def update(self, key: str, value: float) -> RegimeEstimate:
        k = (key or "global").strip().lower()
        s = self.states.setdefault(k, _State())
        x = float(value)
        if not math.isfinite(x):
            return self.estimate(k)
        if s.n == 0:
            s.mean = x
            s.var = 1e-4
            s.n = 1
            return self.estimate(k)

        old_mean = s.mean
        a = self.alpha
        s.mean = (1.0 - a) * s.mean + a * x
        innov = x - old_mean
        s.var = (1.0 - a) * s.var + a * innov * innov
        s.n += 1

        # Two-sided Page-Hinkley magnitude through cumulative demeaned innovation.
        s.ph += innov - self.ph_drift
        s.min_ph = min(s.min_ph, s.ph)
        draw = s.ph - s.min_ph
        vol = math.sqrt(max(s.var, 1e-12))
        shock = abs(innov) > 3.0 * vol
        s.stressed = bool(draw > self.ph_threshold or shock)
        if s.stressed:
            # Reset cumulative statistic after detection so a single shift does not
            # keep the model permanently stressed.
            s.ph = 0.0
            s.min_ph = 0.0
        return self.estimate(k)

    def estimate(self, key: str) -> RegimeEstimate:
        s = self.states.get((key or "global").strip().lower(), _State())
        vol = math.sqrt(max(s.var, 1e-12))
        z = s.mean / vol if vol > 0 else 0.0
        # In stress we shrink stale model information aggressively but never to 0.
        sample_conf = s.n / (s.n + 24.0)
        weight = (0.45 if s.stressed else 1.0) * (0.55 + 0.45 * sample_conf)
        return RegimeEstimate(
            stressed=s.stressed,
            z_score=max(-8.0, min(8.0, z)),
            weight=max(0.20, min(1.0, weight)),
            volatility=vol,
            n=s.n,
        )
