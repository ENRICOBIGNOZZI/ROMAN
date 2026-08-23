from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np

from .hierarchy import HierarchicalFairValueModel
from .factors import RobustPCAFactorModel, residual_discount_overlay
from .kalman import DynamicFactorLayer
from .liquidity import SaleHazardModel
from .seller import SellerQualityModel
from .condition_model import ConditionRiskModel
from .regime import RegimeDetector
from .ensemble import ConservativeEnsemble
from .anomaly import CrossMarketAnomalyModel


@dataclass(frozen=True)
class StackScore:
    trade: bool
    fair_value: float
    acquisition_cost: float
    expected_exit_net: float
    fair_value_net_roi: float
    factor_net_roi: float | None
    anomaly_net_roi: float | None
    locked_net_roi: float | None
    expected_holding_days: float
    sale_prob_30d: float
    seller_success_prob: float
    condition_risk: float
    regime_weight: float
    ensemble_confidence: float
    conservative_net_roi: float
    lcb_net_roi: float
    score_per_capital_day: float
    reason: str


class SimpleModelStack:
    """Interpretable online stack used before any complex ML.

    Candidate monetary fields are assumed to be in one normalized currency
    (EUR in ROMAN after FX conversion). Every ROI produced here is *net* of the
    explicit costs supplied in the candidate dictionary.
    """

    def __init__(self, min_lcb_roi: float = 0.003, lcb_z: float = 1.28):
        self.hierarchy = HierarchicalFairValueModel()
        self.pca = RobustPCAFactorModel()
        self.dynamic_factors = DynamicFactorLayer()
        self.hazard = SaleHazardModel()
        self.sellers = SellerQualityModel()
        self.condition = ConditionRiskModel()
        self.regime = RegimeDetector()
        self.anomaly = CrossMarketAnomalyModel()
        self.ensemble = ConservativeEnsemble(min_signal_roi=min_lcb_roi)
        self.min_lcb_roi = float(min_lcb_roi)
        self.lcb_z = float(lcb_z)

    @staticmethod
    def _f(c: dict, key: str, default: float = 0.0) -> float:
        try:
            x = float(c.get(key, default))
            return x if math.isfinite(x) else float(default)
        except Exception:
            return float(default)

    def observe_execution(
        self,
        *,
        exit_price: float,
        sector: str,
        family: str = "",
        product: str = "",
        seller_route_key: str = "unknown",
        sold: bool = True,
        exposure_days: float = 1.0,
        realized_pnl_roi: float | None = None,
        market_return: float | None = None,
    ) -> None:
        if sold and exit_price > 0:
            self.hierarchy.update(exit_price, sector, family, product)
        segment = "|".join(x for x in (sector, family) if x) or "global"
        self.hazard.update(segment, sold=sold, exposure_days=exposure_days)
        self.sellers.update(
            seller_route_key,
            success=bool(sold and (realized_pnl_roi is None or realized_pnl_roi > 0)),
            realized_pnl_roi=realized_pnl_roi,
        )
        if market_return is not None:
            self.regime.update(sector, market_return)

    def fit_pca(self, returns: np.ndarray, names: list[str] | tuple[str, ...]):
        return self.pca.fit(returns, names)

    def factor_signals(self, latest_returns: dict[str, float]):
        return self.pca.signals(latest_returns)

    def update_dynamic_factors(self, factor_returns: dict[str, float]):
        return self.dynamic_factors.update(factor_returns)

    def score(self, c: dict) -> StackScore:
        buy_price = self._f(c, "buy_price")
        if buy_price <= 0:
            return self._empty("invalid_buy_price")

        buy_fee_rate = self._f(c, "buy_fee_rate")
        acquisition = (
            buy_price * (1.0 + buy_fee_rate)
            + self._f(c, "buy_fixed")
            + self._f(c, "buy_shipping")
            + self._f(c, "buy_tax")
        )

        sector = str(c.get("sector") or "unknown")
        family = str(c.get("family") or "")
        product = str(c.get("product") or c.get("entity_key") or "")
        h = self.hierarchy.predict(sector, family, product)
        base_fair = self._f(c, "base_fair_value", 0.0)
        if base_fair <= 0 and h is None:
            return self._empty("no_fair_value", acquisition=acquisition)
        if base_fair <= 0:
            fair = h.price
        elif h is None:
            fair = base_fair
        else:
            # External executable/market estimate dominates until the hierarchy has
            # substantial evidence; hierarchical estimate can move it by <=50% weight.
            wh = min(0.50, 0.50 * h.confidence)
            fair = (1.0 - wh) * base_fair + wh * h.price

        cond = self.condition.score(
            str(c.get("title") or ""),
            str(c.get("description") or ""),
            c.get("image_count"),
            c.get("image_defect_score"),
        )
        fair *= (1.0 - cond.haircut)

        exit_fee_rate = self._f(c, "exit_fee_rate")
        exit_costs = (
            self._f(c, "exit_fixed")
            + self._f(c, "exit_shipping")
            + self._f(c, "authentication_cost")
            + self._f(c, "fx_cost")
            + self._f(c, "repair_cost")
            + self._f(c, "expected_return_loss")
            + self._f(c, "expected_fraud_loss")
            + self._f(c, "exit_tax")
        )
        exit_net = fair * (1.0 - exit_fee_rate) - exit_costs
        fv_roi = (exit_net - acquisition) / max(acquisition, 1e-9)

        segment = "|".join(x for x in (sector, family) if x) or sector
        price_gap = buy_price / max(fair, 1e-9) - 1.0
        hz = self.hazard.estimate(segment, price_gap=price_gap, quality_risk=cond.risk)

        seller_route = str(c.get("seller_route_key") or c.get("seller_id") or "unknown")
        seller = self.sellers.estimate(seller_route)
        regime = self.regime.estimate(sector)

        factor_roi = None
        if c.get("factor_residual_z") is not None:
            rz = self._f(c, "factor_residual_z")
            rc = self._f(c, "factor_confidence", 0.0)
            adjusted_discount = residual_discount_overlay(0.0, rz, rc)
            factor_roi = fv_roi + adjusted_discount
        elif c.get("factor_net_roi") is not None:
            factor_roi = self._f(c, "factor_net_roi")

        anomaly_roi = None
        if c.get("anomaly_net_roi") is not None:
            anomaly_roi = self._f(c, "anomaly_net_roi")
        elif c.get("cross_market_net_roi") is not None:
            anomaly_roi = self._f(c, "cross_market_net_roi")
        elif isinstance(c.get("comparables_net"), list):
            a = self.anomaly.score(acquisition, c["comparables_net"])
            if a is not None:
                # Shrink anomaly edge by evidence quality rather than treating every
                # public comparable as equally executable.
                anomaly_roi = a.net_roi * a.confidence

        locked_roi = None
        if c.get("locked_net_roi") is not None:
            locked_roi = self._f(c, "locked_net_roi")
        elif self._f(c, "locked_exit_bid", 0.0) > 0:
            bid = self._f(c, "locked_exit_bid")
            locked_net = bid * (1.0 - exit_fee_rate) - exit_costs
            locked_roi = (locked_net - acquisition) / max(acquisition, 1e-9)

        dec = self.ensemble.decide(
            fair_value_roi=fv_roi,
            factor_roi=factor_roi,
            anomaly_roi=anomaly_roi,
            locked_spread_roi=locked_roi,
            seller_success_prob=seller.success_prob,
            condition_risk=cond.risk,
            sale_prob_30d=hz.prob_30d,
            regime_weight=regime.weight,
        )

        base_sigma = self._f(c, "model_sigma_roi", 0.02)
        h_sigma = h.log_sigma if h is not None else 0.0
        # Convert log-price sigma into a capped ROI uncertainty contribution.
        sigma_roi = math.sqrt(base_sigma * base_sigma + min(h_sigma, 0.15) ** 2 + (0.03 * cond.risk) ** 2)
        lcb_roi = dec.conservative_net_roi - self.lcb_z * sigma_roi
        expected_days = min(max(hz.expected_days, 1.0), 365.0)
        score = lcb_roi / expected_days
        trade = bool(dec.trade and lcb_roi > self.min_lcb_roi)
        reason = dec.reason if trade else f"{dec.reason}|lcb_gate"

        return StackScore(
            trade=trade,
            fair_value=fair,
            acquisition_cost=acquisition,
            expected_exit_net=exit_net,
            fair_value_net_roi=fv_roi,
            factor_net_roi=factor_roi,
            anomaly_net_roi=anomaly_roi,
            locked_net_roi=locked_roi,
            expected_holding_days=expected_days,
            sale_prob_30d=hz.prob_30d,
            seller_success_prob=seller.success_prob,
            condition_risk=cond.risk,
            regime_weight=regime.weight,
            ensemble_confidence=dec.confidence,
            conservative_net_roi=dec.conservative_net_roi,
            lcb_net_roi=lcb_roi,
            score_per_capital_day=score,
            reason=reason,
        )

    @staticmethod
    def _empty(reason: str, acquisition: float = 0.0) -> StackScore:
        return StackScore(False, 0.0, acquisition, 0.0, 0.0, None, None, None, 365.0, 0.0, 0.5, 1.0, 0.2, 0.0, 0.0, -1.0, -1.0, reason)
