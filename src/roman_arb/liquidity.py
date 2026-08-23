from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass
class HazardPosterior:
    sales: float = 0.0
    exposure_days: float = 0.0


@dataclass(frozen=True)
class SaleHazardEstimate:
    daily_hazard: float
    expected_days: float
    prob_7d: float
    prob_30d: float
    prob_60d: float
    confidence: float


class SaleHazardModel:
    """Gamma-Poisson sale hazard with conservative covariate multipliers.

    ``price_gap`` means planned exit ask / fair value - 1. It must describe the
    *resale* price, never the acquisition discount. Buying an item cheaply does
    not by itself make the future exit faster.

    The posterior mean hazard is shrunk downward when evidence is weak. This is
    intentional for a small-capital book: cold-start uncertainty should lengthen
    the estimated holding period rather than create artificial capital velocity.
    """

    def __init__(
        self,
        prior_sales: float = 1.5,
        prior_days: float = 30.0,
        cold_start_hazard_multiplier: float = 0.70,
    ):
        self.a0 = float(prior_sales)
        self.b0 = float(prior_days)
        self.cold_start_hazard_multiplier = max(
            0.05, min(1.0, float(cold_start_hazard_multiplier))
        )
        self.stats: dict[str, HazardPosterior] = {}

    @staticmethod
    def _finite(x: float, default: float = 0.0) -> float:
        try:
            v = float(x)
            return v if math.isfinite(v) else float(default)
        except Exception:
            return float(default)

    def update(self, segment: str, sold: bool, exposure_days: float) -> None:
        key = (segment or "global").strip().lower()
        s = self.stats.setdefault(key, HazardPosterior())
        exposure = max(self._finite(exposure_days), 0.0)
        s.exposure_days += exposure
        if sold:
            s.sales += 1.0

    def estimate(
        self,
        segment: str,
        price_gap: float = 0.0,
        quality_risk: float = 0.0,
    ) -> SaleHazardEstimate:
        key = (segment or "global").strip().lower()
        s = self.stats.get(key, HazardPosterior())

        posterior_mean = (self.a0 + s.sales) / max(
            self.b0 + s.exposure_days, 1e-9
        )
        evidence = s.exposure_days + 10.0 * s.sales
        confidence = evidence / (evidence + 60.0)

        # A weakly identified segment receives a conservative speed haircut.
        uncertainty_mult = self.cold_start_hazard_multiplier + (
            1.0 - self.cold_start_hazard_multiplier
        ) * confidence

        gap = max(-0.50, min(0.50, self._finite(price_gap)))
        risk = max(0.0, min(1.0, self._finite(quality_risk)))
        # Positive exit gap slows sales; a deliberate markdown accelerates them.
        price_mult = math.exp(max(-0.8, min(0.8, -2.0 * gap)))
        quality_mult = math.exp(max(-0.7, min(0.0, -1.5 * risk)))

        lam = posterior_mean * uncertainty_mult * price_mult * quality_mult
        lam = max(1.0 / 365.0, min(0.5, lam))
        expected = 1.0 / lam

        def p(h: float) -> float:
            return 1.0 - math.exp(-lam * h)

        return SaleHazardEstimate(
            daily_hazard=lam,
            expected_days=expected,
            prob_7d=p(7.0),
            prob_30d=p(30.0),
            prob_60d=p(60.0),
            confidence=max(0.0, min(1.0, confidence)),
        )
