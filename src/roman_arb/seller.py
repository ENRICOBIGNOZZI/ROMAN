from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BetaPosterior:
    alpha: float = 2.0
    beta: float = 2.0
    pnl_sum: float = 0.0
    pnl_n: int = 0

    @property
    def success_prob(self) -> float:
        return self.alpha / max(self.alpha + self.beta, 1e-9)

    @property
    def mean_pnl_roi(self) -> float:
        return self.pnl_sum / max(self.pnl_n, 1)


@dataclass(frozen=True)
class SellerQualityEstimate:
    success_prob: float
    mean_pnl_roi: float
    confidence: float
    risk_penalty_roi: float


class SellerQualityModel:
    """Beta-Binomial seller/route reliability posterior.

    Keys are deliberately flexible: use seller id alone or a composite such as
    ``seller|buy_venue|exit_venue``.  A small prior prevents a new seller from
    looking either perfect or terrible after one observation.
    """

    def __init__(self, prior_alpha: float = 2.0, prior_beta: float = 2.0, max_penalty_roi: float = 0.06):
        self.prior_alpha = float(prior_alpha)
        self.prior_beta = float(prior_beta)
        self.max_penalty_roi = float(max_penalty_roi)
        self.stats: dict[str, BetaPosterior] = {}

    def _get(self, key: str) -> BetaPosterior:
        k = (key or "unknown").strip().lower()
        if k not in self.stats:
            self.stats[k] = BetaPosterior(self.prior_alpha, self.prior_beta)
        return self.stats[k]

    def update(self, key: str, success: bool, realized_pnl_roi: float | None = None, weight: float = 1.0) -> None:
        s = self._get(key)
        w = max(float(weight), 0.0)
        if success:
            s.alpha += w
        else:
            s.beta += w
        if realized_pnl_roi is not None:
            s.pnl_sum += float(realized_pnl_roi)
            s.pnl_n += 1

    def estimate(self, key: str) -> SellerQualityEstimate:
        s = self._get(key)
        p = s.success_prob
        evidence = max((s.alpha + s.beta) - (self.prior_alpha + self.prior_beta), 0.0)
        confidence = evidence / (evidence + 12.0)
        # Only reliability below 70% gets a material penalty. New sellers receive
        # a modest penalty because their posterior remains close to 50%.
        shortfall = max(0.0, 0.70 - p) / 0.70
        penalty = self.max_penalty_roi * shortfall * (0.5 + 0.5 * confidence)
        return SellerQualityEstimate(
            success_prob=p,
            mean_pnl_roi=s.mean_pnl_roi,
            confidence=confidence,
            risk_penalty_roi=penalty,
        )
