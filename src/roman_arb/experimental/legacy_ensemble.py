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
    """Dependence-aware gate for already-net ROI evidence.

    A fresh locked/executable spread is a distinct economic object and may bypass
    model consensus because the exit itself supplies execution/liquidity evidence.

    For inventory forecasts, ROMAN must not count several transformations of the
    same cross-market comparables as independent model votes. The fair-value ROI is
    the base valuation channel. The factor channel only confirms it when it adds a
    *positive, non-trivial* temporal residual adjustment. A cross-market anomaly is
    retained as diagnostic evidence but is not, by default, an independent vote.
    This deliberately reduces cold-start trading rather than manufacture agreement.
    """

    def __init__(
        self,
        min_signal_roi: float = 0.004,
        min_agreement: float = 2 / 3,
        min_confidence: float = 0.22,
        min_factor_confirmation_roi: float = 0.0005,
    ):
        self.min_signal_roi = float(min_signal_roi)
        self.min_agreement = float(min_agreement)
        self.min_confidence = float(min_confidence)
        self.min_factor_confirmation_roi = max(
            0.0, float(min_factor_confirmation_roi)
        )

    @staticmethod
    def _clip01(x: float, default: float) -> float:
        try:
            v = float(x)
            if not math.isfinite(v):
                v = default
        except Exception:
            v = default
        return max(0.0, min(1.0, v))

    @staticmethod
    def _finite_or_none(x: float | None) -> float | None:
        if x is None:
            return None
        try:
            v = float(x)
        except Exception:
            return None
        return v if math.isfinite(v) else None

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
        anomaly_independent: bool = False,
    ) -> EnsembleDecision:
        fair = self._finite_or_none(fair_value_roi)
        factor = self._finite_or_none(factor_roi)
        anomaly = self._finite_or_none(anomaly_roi)
        locked = self._finite_or_none(locked_spread_roi)

        seller = self._clip01(seller_success_prob, 0.5)
        condition = self._clip01(condition_risk, 0.2)
        liquidity = self._clip01(sale_prob_30d, 0.5)
        regime = self._clip01(regime_weight, 0.55)

        # Bounded risk haircuts. Seller reliability also contributes an additive
        # uncertainty penalty in the stack's LCB calculation.
        seller_gate = 0.75 + 0.25 * seller
        condition_gate = 1.0 - 0.50 * condition
        regime_gate = 0.70 + 0.30 * regime
        liquidity_gate = 0.65 + 0.35 * liquidity

        if locked is not None and locked > self.min_signal_roi:
            # A fresh executable exit makes the inventory sale-hazard forecast
            # irrelevant, but seller/condition/regime safeguards remain active.
            quality_gate = seller_gate * condition_gate * regime_gate
            conservative = locked * quality_gate
            conf = min(1.0, 0.65 + 0.35 * quality_gate)
            trade = (
                conservative > self.min_signal_roi
                and seller >= 0.45
                and condition <= 0.65
            )
            return EnsembleDecision(
                trade,
                locked,
                conservative,
                conf,
                1.0,
                "locked_executable" if trade else "locked_but_quality_gate",
            )

        if fair is None:
            return EnsembleDecision(
                False, 0.0, 0.0, 0.0, 0.0, "missing_fair_value_signal"
            )

        # In the current stack factor_roi = fair_roi + bounded temporal residual
        # overlay. Its *increment* is the independent information. Merely copying
        # a positive fair-value ROI into the factor channel is not confirmation.
        factor_increment = None if factor is None else factor - fair
        factor_confirms = (
            factor_increment is not None
            and factor_increment >= self.min_factor_confirmation_roi
        )
        if not factor_confirms:
            return EnsembleDecision(
                False,
                fair,
                0.0,
                0.0,
                0.0,
                "insufficient_independent_confirmation",
            )

        # Use only evidence channels that can legitimately vote. A positive
        # anomaly computed from the same comparables is diagnostic, not another
        # vote. Callers may explicitly mark a separately-estimated anomaly model
        # as independent in the future.
        decision_signals = [fair, factor]
        if anomaly_independent and anomaly is not None:
            decision_signals.append(anomaly)

        positives = sum(x > self.min_signal_roi for x in decision_signals)
        agreement = positives / len(decision_signals)
        arr = np.asarray(decision_signals, dtype=float)
        q25 = float(np.quantile(arr, 0.25))
        med = float(np.median(arr))
        expected = 0.5 * q25 + 0.5 * med

        quality_gate = seller_gate * condition_gate * liquidity_gate * regime_gate
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
