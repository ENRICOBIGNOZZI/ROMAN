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
    """Simple Gamma-Poisson sale hazard with transparent covariate multipliers.

    Segment can be sector/family/product-route.  The base hazard posterior is
    (a0 + sales)/(b0 + exposure_days).  Pricing and quality covariates only apply
    bounded multiplicative adjustments so the model cannot create extreme speed.
    """

    def __init__(self, prior_sales: float = 1.5, prior_days: float = 30.0):
        self.a0 = float(prior_sales)
        self.b0 = float(prior_days)
        self.stats: dict[str, HazardPosterior] = {}

    def update(self, segment: str, sold: bool, exposure_days: float) -> None:
        key = (segment or "global").strip().lower()
        s = self.stats.setdefault(key, HazardPosterior())
        s.exposure_days += max(float(exposure_days), 0.0)
        if sold:
            s.sales += 1.0

    def estimate(self, segment: str, price_gap: float = 0.0, quality_risk: float = 0.0) -> SaleHazardEstimate:
        key = (segment or "global").strip().lower()
        s = self.stats.get(key, HazardPosterior())
        lam = (self.a0 + s.sales) / max(self.b0 + s.exposure_days, 1e-9)
        # price_gap = ask/fair - 1. Positive gap slows sales; discount accelerates.
        price_mult = math.exp(max(-0.8, min(0.8, -2.0 * float(price_gap))))
        quality_mult = math.exp(max(-0.7, min(0.0, -1.5 * max(float(quality_risk), 0.0))))
        lam = max(1.0 / 365.0, min(0.5, lam * price_mult * quality_mult))
        expected = 1.0 / lam
        p = lambda h: 1.0 - math.exp(-lam * h)
        evidence = s.exposure_days + 10.0 * s.sales
        confidence = evidence / (evidence + 60.0)
        return SaleHazardEstimate(
            daily_hazard=lam,
            expected_days=expected,
            prob_7d=p(7.0),
            prob_30d=p(30.0),
            prob_60d=p(60.0),
            confidence=max(0.0, min(1.0, confidence)),
        )
