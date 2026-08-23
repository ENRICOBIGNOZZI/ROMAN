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
from .anomaly import CrossMarketAnomalyModel


@dataclass(frozen=True)
class PredictiveDistribution:
    fair_value: float
    acquisition_cost: float
    fair_value_net_roi: float
    expected_exit_net: float
    expected_net_roi: float
    sigma_net_roi: float
    expected_holding_days: float
    sale_prob_30d: float
    seller_success_prob: float
    condition_risk: float
    regime_weight: float
    confidence: float
    factor_net_roi: float | None
    anomaly_net_roi: float | None
    locked_net_roi: float | None


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
    """One predictive resale model: payoff + time-to-sale -> decision."""

    def __init__(self, min_lcb_roi: float = 0.003, lcb_z: float = 1.28):
        self.hierarchy = HierarchicalFairValueModel()
        self.pca = RobustPCAFactorModel()
        self.dynamic_factors = DynamicFactorLayer()
        self.hazard = SaleHazardModel()
        self.sellers = SellerQualityModel()
        self.condition = ConditionRiskModel()
        self.regime = RegimeDetector()
        self.anomaly = CrossMarketAnomalyModel()
        self.min_lcb_roi = float(min_lcb_roi)
        self.lcb_z = float(lcb_z)

    @staticmethod
    def _f(c: dict, key: str, default: float = 0.0) -> float:
        try:
            x = float(c.get(key, default))
            return x if math.isfinite(x) else float(default)
        except Exception:
            return float(default)

    @staticmethod
    def _clip(x: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, float(x)))

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

    def _factor_adjustment(self, c: dict, fv_roi: float, regime_weight: float) -> tuple[float, float | None]:
        adj = 0.0
        diagnostic = None
        if c.get("factor_residual_z") is not None:
            adj = residual_discount_overlay(
                0.0,
                self._f(c, "factor_residual_z"),
                self._f(c, "factor_confidence", 0.0),
                max_adjustment=0.02,
            )
        elif c.get("factor_net_roi") is not None:
            adj = self._f(c, "factor_net_roi") - fv_roi
        elif isinstance(c.get("factor_loadings"), dict) and c.get("item_return") is not None:
            loadings = {str(k): float(v) for k, v in c["factor_loadings"].items()}
            common, common_sigma = self.dynamic_factors.common_return(loadings)
            scale = max(common_sigma, self._f(c, "factor_residual_scale", 0.02), 0.005)
            rz = (self._f(c, "item_return") - common) / scale
            initialized = sum(
                1 for k in loadings
                if k in self.dynamic_factors.filters and self.dynamic_factors.filters[k].state.initialized
            )
            confidence = initialized / max(len(loadings), 1)
            adj = residual_discount_overlay(0.0, rz, confidence, max_adjustment=0.02)
        if adj != 0.0 or c.get("factor_net_roi") is not None or c.get("factor_residual_z") is not None:
            adj = self._clip(adj, -0.02, 0.02)
            diagnostic = fv_roi + adj
        return adj * regime_weight, diagnostic

    def predict(self, c: dict) -> PredictiveDistribution | None:
        buy_price = self._f(c, "buy_price")
        if buy_price <= 0:
            return None
        acquisition = (
            buy_price * (1.0 + self._f(c, "buy_fee_rate"))
            + self._f(c, "buy_fixed")
            + self._f(c, "buy_shipping")
            + self._f(c, "buy_tax")
        )
        if acquisition <= 0:
            return None

        sector = str(c.get("sector") or "unknown")
        family = str(c.get("family") or "")
        product = str(c.get("product") or c.get("entity_key") or "")
        h = self.hierarchy.predict(sector, family, product)
        base_fair = self._f(c, "base_fair_value")
        if base_fair <= 0 and h is None:
            return None
        if base_fair <= 0:
            fair, h_weight = h.price, 1.0
        elif h is None:
            fair, h_weight = base_fair, 0.0
        else:
            h_weight = min(0.50, 0.50 * h.confidence)
            fair = (1.0 - h_weight) * base_fair + h_weight * h.price

        cond = self.condition.score(
            str(c.get("title") or ""),
            str(c.get("description") or ""),
            c.get("image_count"),
            c.get("image_defect_score"),
        )
        fair *= 1.0 - cond.haircut

        exit_fee = self._f(c, "exit_fee_rate")
        exit_costs = sum(self._f(c, k) for k in (
            "exit_fixed", "exit_shipping", "authentication_cost", "fx_cost",
            "repair_cost", "expected_return_loss", "expected_fraud_loss", "exit_tax",
        ))
        fair_exit_net = fair * (1.0 - exit_fee) - exit_costs
        fv_roi = (fair_exit_net - acquisition) / acquisition

        seller_key = str(c.get("seller_route_key") or c.get("seller_id") or "unknown")
        seller = self.sellers.estimate(seller_key)
        regime = self.regime.estimate(sector)

        factor_adj, factor_roi = self._factor_adjustment(c, fv_roi, regime.weight)
        expected_exit_net = fair_exit_net + acquisition * factor_adj

        anomaly_roi = None
        anomaly_conf = 0.0
        anomaly_gap = 0.0
        reference_net = None
        if c.get("anomaly_net_roi") is not None:
            anomaly_roi = self._f(c, "anomaly_net_roi")
            anomaly_conf = self._clip(self._f(c, "anomaly_confidence", 0.40), 0.0, 1.0)
            reference_net = acquisition * (1.0 + anomaly_roi)
        elif c.get("cross_market_net_roi") is not None:
            anomaly_roi = self._f(c, "cross_market_net_roi")
            anomaly_conf = self._clip(self._f(c, "anomaly_confidence", 0.40), 0.0, 1.0)
            reference_net = acquisition * (1.0 + anomaly_roi)
        elif isinstance(c.get("comparables_net"), list):
            a = self.anomaly.score(acquisition, c["comparables_net"])
            if a is not None:
                anomaly_roi, anomaly_conf, reference_net = a.net_roi, a.confidence, a.reference_net_value

        if reference_net is not None and anomaly_roi is not None:
            current_roi = (expected_exit_net - acquisition) / acquisition
            anomaly_gap = abs(anomaly_roi - current_roi)
            w = min(0.55, 0.55 * anomaly_conf)
            expected_exit_net = (1.0 - w) * expected_exit_net + w * reference_net

        locked_roi = None
        if c.get("locked_net_roi") is not None:
            locked_roi = self._f(c, "locked_net_roi")
        elif self._f(c, "locked_exit_bid") > 0:
            locked_net = self._f(c, "locked_exit_bid") * (1.0 - exit_fee) - exit_costs
            locked_roi = (locked_net - acquisition) / acquisition

        locked = locked_roi is not None
        if locked:
            expected_exit_net = acquisition * (1.0 + locked_roi)
        else:
            expected_exit_net = acquisition + regime.weight * (expected_exit_net - acquisition)

        expected_exit_net -= acquisition * seller.risk_penalty_roi
        expected_roi = (expected_exit_net - acquisition) / acquisition

        segment = "|".join(x for x in (sector, family) if x) or sector
        if locked:
            expected_days = max(1.0, self._f(c, "locked_holding_days", 1.0))
            sale30 = self._clip(self._f(c, "locked_exit_probability", 0.97), 0.0, 1.0)
            hazard_conf = sale30
        else:
            target_exit = self._f(c, "target_exit_price", fair)
            if target_exit <= 0:
                target_exit = fair
            gap = target_exit / max(fair, 1e-9) - 1.0
            hz = self.hazard.estimate(segment, price_gap=gap, quality_risk=cond.risk)
            expected_days = min(max(hz.expected_days, 1.0), 365.0)
            sale30, hazard_conf = hz.prob_30d, hz.confidence

        base_sigma = max(self._f(c, "model_sigma_roi", 0.02), 0.0)
        if locked:
            valuation_sigma, hierarchy_sigma, anomaly_sigma, regime_sigma = min(base_sigma, 0.005), 0.0, 0.0, 0.0
        else:
            valuation_sigma = base_sigma
            hierarchy_sigma = 0.0 if h is None else min(h.log_sigma, 0.15) * (1.0 if base_fair <= 0 else max(h_weight, 0.20))
            anomaly_sigma = 0.25 * anomaly_gap * (1.0 - 0.5 * anomaly_conf)
            regime_sigma = 0.02 * (1.0 - regime.weight)
        sigma = math.sqrt(
            valuation_sigma ** 2
            + hierarchy_sigma ** 2
            + anomaly_sigma ** 2
            + (0.03 * cond.risk) ** 2
            + (0.04 * (1.0 - seller.success_prob)) ** 2
            + regime_sigma ** 2
        )
        price_conf = 1.0 / (1.0 + 8.0 * sigma)
        confidence = self._clip(0.75 * price_conf + 0.25 * hazard_conf, 0.0, 1.0)

        return PredictiveDistribution(
            fair, acquisition, fv_roi, expected_exit_net, expected_roi, sigma,
            expected_days, sale30, seller.success_prob, cond.risk, regime.weight,
            confidence, factor_roi, anomaly_roi, locked_roi,
        )

    def score(self, c: dict) -> StackScore:
        p = self.predict(c)
        if p is None:
            buy = self._f(c, "buy_price")
            if buy <= 0:
                return self._empty("invalid_buy_price")
            acquisition = buy * (1.0 + self._f(c, "buy_fee_rate")) + self._f(c, "buy_fixed") + self._f(c, "buy_shipping") + self._f(c, "buy_tax")
            return self._empty("no_fair_value", acquisition)

        lcb = p.expected_net_roi - self.lcb_z * p.sigma_net_roi
        score = lcb / max(p.expected_holding_days, 1.0)
        seller_ok = p.seller_success_prob >= 0.45
        condition_ok = p.condition_risk <= 0.65
        trade = bool(lcb > self.min_lcb_roi and seller_ok and condition_ok)
        if not seller_ok:
            reason = "seller_quality_gate"
        elif not condition_ok:
            reason = "condition_risk_gate"
        elif lcb <= self.min_lcb_roi:
            reason = "unified_lcb_gate"
        elif p.locked_net_roi is not None:
            reason = "locked_exit_unified_lcb"
        else:
            reason = "unified_predictive_lcb"

        return StackScore(
            trade, p.fair_value, p.acquisition_cost, p.expected_exit_net,
            p.fair_value_net_roi, p.factor_net_roi, p.anomaly_net_roi,
            p.locked_net_roi, p.expected_holding_days, p.sale_prob_30d,
            p.seller_success_prob, p.condition_risk, p.regime_weight, p.confidence,
            p.expected_net_roi, lcb, score, reason,
        )

    @staticmethod
    def _empty(reason: str, acquisition: float = 0.0) -> StackScore:
        return StackScore(False, 0.0, acquisition, 0.0, 0.0, None, None, None, 365.0, 0.0, 0.5, 1.0, 0.2, 0.0, 0.0, -1.0, -1.0, reason)
