from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class EnsembleDecision:
    trade: bool
    expected_net_roi: float
    conservative_net_roi: float
    confidence: float
    agreement: float
    reason: str


class ConservativeEnsemble:
    """Agreement-gated ensemble for already-net ROI signals.

    Signals should already include venue fees, shipping, FX, authentication and
    expected operational loss.  Locked/executable spread is treated separately:
    it can bypass model agreement, but never seller/condition/liquidity gates.
    """

    def __init__(self, min_signal_roi: float = 0.004, min_agreement: float = 2 / 3, min_confidence: float = 0.22):
        self.min_signal_roi = float(min_signal_roi)
        self.min_agreement = float(min_agreement)
        self.min_confidence = float(min_confidence)

    def decide(
        self,
        fair_value_roi: float | None,
        factor_roi: float | None,
        anomaly_roi: float | None,
        locked_spread_roi: float | None = None,
        seller_success_prob: float = 0.5,
        condition_risk: float = 0.2,
        sale_prob_30d: float = 0.5,
        regime_weight: float = 1.0,
    ) -> EnsembleDecision:
        model_signals = [float(x) for x in (fair_value_roi, factor_roi, anomaly_roi) if x is not None and math.isfinite(float(x))]
        locked = float(locked_spread_roi) if locked_spread_roi is not None and math.isfinite(float(locked_spread_roi)) else None

        seller = max(0.0, min(1.0, float(seller_success_prob)))
        condition = max(0.0, min(1.0, float(condition_risk)))
        liquidity = max(0.0, min(1.0, float(sale_prob_30d)))
        regime = max(0.0, min(1.0, float(regime_weight)))
        quality_gate = seller * (1.0 - condition) * (0.35 + 0.65 * liquidity) * regime

        if locked is not None and locked > self.min_signal_roi:
            conservative = locked * quality_gate
            conf = min(1.0, 0.65 + 0.35 * quality_gate)
            trade = conservative > self.min_signal_roi and seller >= 0.45 and condition <= 0.65
            return EnsembleDecision(trade, locked, conservative, conf, 1.0, "locked_executable" if trade else "locked_but_quality_gate")

        if len(model_signals) < 2:
            return EnsembleDecision(False, 0.0, 0.0, 0.0, 0.0, "insufficient_model_agreement")

        positives = sum(x > self.min_signal_roi for x in model_signals)
        agreement = positives / len(model_signals)
        arr = np.asarray(model_signals, dtype=float)
        # Conservative location: halfway between lower quartile and median.
        q25 = float(np.quantile(arr, 0.25))
        med = float(np.median(arr))
        expected = 0.5 * q25 + 0.5 * med
        conservative = expected * quality_gate
        conf = agreement * quality_gate

        trade = (
            agreement >= self.min_agreement
            and conf >= self.min_confidence
            and conservative > self.min_signal_roi
            and seller >= 0.45
            and condition <= 0.65
        )
        reason = "model_consensus" if trade else "ensemble_gate"
        return EnsembleDecision(trade, expected, conservative, conf, agreement, reason)
