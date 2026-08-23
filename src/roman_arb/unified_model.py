from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .anomaly import CrossMarketAnomalyModel
from .condition_model import ConditionRiskModel
from .factors import RobustPCAFactorModel, residual_discount_overlay
from .hierarchy import HierarchicalFairValueModel
from .kalman import DynamicFactorLayer
from .liquidity import SaleHazardModel
from .regime import RegimeDetector
from .seller import SellerQualityModel


@dataclass(frozen=True)
class PredictiveDistribution:
    """The single payoff/time distribution used by the decision rule."""

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
    """Compatibility-facing decision output.

    ``ensemble_confidence`` is the historical field name; it now means confidence
    in this one predictive distribution. ``conservative_net_roi`` is the LCB.
    """

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

    @property
    def predictive_confidence(self) -> float:
        return self.ensemble_confidence


class SimpleModelStack:
    """Unified resale model: evidence -> payoff/time distribution -> one LCB.

    The components are covariates or measurements of one economic object, not
    independent models that vote. Legacy pre-computed ROI signals are ignored by
    the production decision path.
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
        self.min_lcb_roi = float(min_lcb_roi)
        self.lcb_z = float(lcb_z)

    @staticmethod
    def _f(c: dict, key: str, default: float = 0.0) -> float:
        try:
            value = float(c.get(key, default))
            return value if math.isfinite(value) else float(default)
        except Exception:
            return float(default)

    @staticmethod
    def _clip(x: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, float(x)))

    @staticmethod
    def _weighted_median(rows: list[tuple[float, float]]) -> float | None:
        clean = []
        for value, weight in rows:
            try:
                v, w = float(value), float(weight)
            except Exception:
                continue
            if math.isfinite(v) and v > 0 and math.isfinite(w) and w > 0:
                clean.append((v, w))
        clean.sort()
        if not clean:
            return None
        total = sum(w for _, w in clean)
        running = 0.0
        for value, weight in clean:
            running += weight
            if running >= 0.5 * total:
                return value
        return clean[-1][0]

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
        seller_success: bool | None = None,
        realized_pnl_roi: float | None = None,
        market_return: float | None = None,
    ) -> None:
        """Update online state from genuine forward outcomes only.

        Realized P&L is intentionally not a seller-quality label. An explicit
        ``seller_success`` outcome is required to update that posterior.
        """
        try:
            px = float(exit_price)
        except Exception:
            px = float("nan")
        if sold and math.isfinite(px) and px > 0:
            self.hierarchy.update(
                px,
                sector,
                family,
                product,
                trusted=True,
            )

        segment = "|".join(x for x in (sector, family) if x) or "global"
        self.hazard.update(
            segment,
            sold=bool(sold),
            exposure_days=max(self._f({"x": exposure_days}, "x"), 0.0),
        )

        if seller_success is not None:
            self.sellers.update(
                seller_route_key,
                success=bool(seller_success),
                realized_pnl_roi=None,
            )

        if market_return is not None:
            try:
                ret = float(market_return)
            except Exception:
                ret = float("nan")
            if math.isfinite(ret):
                self.regime.update(sector, ret)

    def fit_pca(self, returns: np.ndarray, names: list[str] | tuple[str, ...]):
        return self.pca.fit(returns, names)

    def factor_signals(self, latest_returns: dict[str, float]):
        return self.pca.signals(latest_returns)

    def update_dynamic_factors(self, factor_returns: dict[str, float]):
        return self.dynamic_factors.update(factor_returns)

    def _factor_adjustment(
        self,
        c: dict,
        baseline_roi: float,
    ) -> tuple[float, float | None]:
        """Bounded adjustment from raw temporal/state information only."""
        adjustment = 0.0
        observed = False

        if c.get("factor_residual_z") is not None:
            observed = True
            adjustment = residual_discount_overlay(
                0.0,
                self._f(c, "factor_residual_z"),
                self._clip(self._f(c, "factor_confidence", 0.0), 0.0, 1.0),
                max_adjustment=0.02,
            )
        elif isinstance(c.get("factor_loadings"), dict) and c.get("item_return") is not None:
            loadings: dict[str, float] = {}
            for key, value in c["factor_loadings"].items():
                try:
                    v = float(value)
                except Exception:
                    continue
                if math.isfinite(v):
                    loadings[str(key)] = v
            if loadings:
                observed = True
                common, common_sigma = self.dynamic_factors.common_return(loadings)
                scale = max(
                    float(common_sigma),
                    self._f(c, "factor_residual_scale", 0.02),
                    0.005,
                )
                residual_z = (self._f(c, "item_return") - float(common)) / scale
                initialized = sum(
                    1
                    for key in loadings
                    if key in self.dynamic_factors.filters
                    and self.dynamic_factors.filters[key].state.initialized
                )
                confidence = initialized / max(len(loadings), 1)
                adjustment = residual_discount_overlay(
                    0.0,
                    residual_z,
                    confidence,
                    max_adjustment=0.02,
                )

        # ``factor_net_roi`` was a legacy model vote. It cannot affect the core.
        adjustment = self._clip(adjustment, -0.02, 0.02)
        diagnostic = baseline_roi + adjustment if observed else None
        return adjustment, diagnostic

    def _selected_route_observation(self, c: dict) -> tuple[float | None, float]:
        """Return net-cash evidence for the concrete selected exit route."""
        comparables = c.get("comparables_net")
        exit_source = str(c.get("exit_source") or "")
        if not isinstance(comparables, list) or not exit_source:
            return None, 0.0

        rows: list[tuple[float, float]] = []
        effective_weight = 0.0
        for comp in comparables:
            if not isinstance(comp, dict):
                continue
            if str(comp.get("source") or "") != exit_source:
                continue
            try:
                value = float(comp.get("net_value"))
                freshness = float(comp.get("freshness", 1.0))
                executable = float(comp.get("executable_confidence", 1.0))
                weight = float(comp.get("weight", 1.0))
            except Exception:
                continue
            if not math.isfinite(value) or value <= 0:
                continue
            weight *= self._clip(freshness, 0.0, 1.0)
            weight *= self._clip(executable, 0.0, 1.0)
            if weight <= 0:
                continue
            rows.append((value, weight))
            effective_weight += weight

        value = self._weighted_median(rows)
        if value is None:
            return None, 0.0
        confidence = 1.0 - math.exp(-max(effective_weight, 0.0))
        return value, self._clip(confidence, 0.0, 1.0)

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
        if acquisition <= 0 or not math.isfinite(acquisition):
            return None

        sector = str(c.get("sector") or "unknown")
        family = str(c.get("family") or "")
        product = str(c.get("product") or c.get("entity_key") or "")
        hierarchy = self.hierarchy.predict(sector, family, product)
        base_fair = self._f(c, "base_fair_value")
        if base_fair <= 0 and hierarchy is None:
            return None
        if base_fair <= 0:
            fair_raw = hierarchy.price
            hierarchy_weight = 1.0
        elif hierarchy is None:
            fair_raw = base_fair
            hierarchy_weight = 0.0
        else:
            hierarchy_weight = min(0.50, 0.50 * hierarchy.confidence)
            fair_raw = (
                (1.0 - hierarchy_weight) * base_fair
                + hierarchy_weight * hierarchy.price
            )

        condition = self.condition.score(
            str(c.get("title") or ""),
            str(c.get("description") or ""),
            c.get("image_count"),
            c.get("image_defect_score"),
        )
        fair = fair_raw * (1.0 - condition.haircut)

        exit_fee = self._clip(self._f(c, "exit_fee_rate"), 0.0, 0.95)
        route_costs = sum(
            self._f(c, key)
            for key in ("exit_fixed", "exit_shipping", "fx_cost")
        )
        operational_losses = sum(
            self._f(c, key)
            for key in (
                "authentication_cost",
                "repair_cost",
                "expected_return_loss",
                "expected_fraud_loss",
                "exit_tax",
            )
        )
        fair_route_net = (
            fair * (1.0 - exit_fee)
            - route_costs
            - operational_losses
        )

        seller_key = str(c.get("seller_route_key") or c.get("seller_id") or "unknown")
        seller = self.sellers.estimate(seller_key)
        regime = self.regime.estimate(sector)

        route_net, route_confidence = self._selected_route_observation(c)
        if route_net is not None:
            # ``net_value`` already contains that route's marketplace/FX/shipping
            # economics. Do not charge the route costs a second time.
            baseline_exit_net = (
                route_net * (1.0 - condition.haircut)
                - operational_losses
            )
        else:
            baseline_exit_net = fair_route_net

        anomaly_roi = None
        anomaly_confidence = 0.0
        anomaly_gap = 0.0
        comparables = c.get("comparables_net")
        if isinstance(comparables, list):
            anomaly = self.anomaly.score(acquisition, comparables)
            if anomaly is not None:
                anomaly_confidence = self._clip(anomaly.confidence, 0.0, 1.0)
                anomaly_reference = (
                    anomaly.reference_net_value * (1.0 - condition.haircut)
                    - operational_losses
                )
                anomaly_roi = (anomaly_reference - acquisition) / acquisition
                anomaly_gap = abs(
                    anomaly_roi
                    - (baseline_exit_net - acquisition) / acquisition
                )
                # Other marketplaces are noisy measurements of the same value.
                # If the selected route itself has a net observation, that route
                # owns P&L and the cross-market estimate remains diagnostic only.
                if route_net is None:
                    weight = min(0.55, 0.55 * anomaly_confidence)
                    baseline_exit_net = (
                        (1.0 - weight) * baseline_exit_net
                        + weight * anomaly_reference
                    )

        baseline_roi = (baseline_exit_net - acquisition) / acquisition
        factor_adjustment, factor_roi = self._factor_adjustment(c, baseline_roi)

        locked = False
        locked_roi = None
        locked_bid = self._f(c, "locked_exit_bid")
        if locked_bid > 0:
            locked_net = (
                locked_bid
                * (1.0 - condition.haircut)
                * (1.0 - exit_fee)
                - route_costs
                - operational_losses
            )
            locked_roi = (locked_net - acquisition) / acquisition
            locked = bool(c.get("locked", True))
        elif c.get("locked_net_roi") is not None and bool(c.get("locked")):
            # Explicit compatibility escape hatch only; a naked legacy ROI cannot
            # manufacture an executable opportunity.
            locked_roi = self._f(c, "locked_net_roi")
            locked = True

        if locked and locked_roi is not None:
            expected_exit_net = acquisition * (1.0 + locked_roi)
        else:
            expected_exit_net = baseline_exit_net + acquisition * factor_adjustment
            if route_net is None:
                # Regime uncertainty shrinks a model-based forecast toward break-
                # even. Direct route cash evidence is not rewritten by a separate
                # regime model; regime risk enters its uncertainty instead.
                expected_exit_net = acquisition + regime.weight * (
                    expected_exit_net - acquisition
                )

        # Seller quality is a risk input, not a second expected-PnL model. Keep the
        # mean economically interpretable and carry seller uncertainty into sigma.
        expected_roi = (expected_exit_net - acquisition) / acquisition

        segment = "|".join(x for x in (sector, family) if x) or sector
        if locked:
            expected_days = max(1.0, self._f(c, "locked_holding_days", 1.0))
            sale_prob_30d = self._clip(
                self._f(c, "locked_exit_probability", 0.97),
                0.0,
                1.0,
            )
            hazard_confidence = sale_prob_30d
        else:
            target_exit = self._f(
                c,
                "target_exit_price",
                self._f(c, "planned_exit_price", fair),
            )
            if target_exit <= 0:
                target_exit = fair
            gap = target_exit / max(fair, 1e-9) - 1.0
            hazard = self.hazard.estimate(
                segment,
                price_gap=gap,
                quality_risk=condition.risk,
            )
            expected_days = min(max(hazard.expected_days, 1.0), 365.0)
            sale_prob_30d = self._clip(hazard.prob_30d, 0.0, 1.0)
            hazard_confidence = self._clip(hazard.confidence, 0.0, 1.0)

        base_sigma = max(self._f(c, "model_sigma_roi", 0.02), 0.0)
        if locked:
            valuation_sigma = min(max(base_sigma, 0.001), 0.005)
            hierarchy_sigma = 0.0
            anomaly_sigma = 0.0
            regime_sigma = 0.0
        else:
            if route_net is not None:
                valuation_sigma = max(
                    0.005,
                    base_sigma * (1.0 - 0.60 * route_confidence),
                )
                hierarchy_sigma = 0.0
            else:
                valuation_sigma = base_sigma
                hierarchy_sigma = (
                    0.0
                    if hierarchy is None
                    else min(hierarchy.log_sigma, 0.15)
                    * (
                        1.0
                        if base_fair <= 0
                        else max(hierarchy_weight, 0.20)
                    )
                )
            anomaly_sigma = (
                0.25 * anomaly_gap * (1.0 - 0.5 * anomaly_confidence)
                if anomaly_roi is not None
                else 0.0
            )
            regime_sigma = 0.02 * (1.0 - regime.weight)

        seller_sigma = max(
            0.04 * (1.0 - seller.success_prob),
            seller.risk_penalty_roi,
        )
        sigma = math.sqrt(
            valuation_sigma**2
            + hierarchy_sigma**2
            + anomaly_sigma**2
            + (0.03 * condition.risk) ** 2
            + seller_sigma**2
            + regime_sigma**2
        )
        if not math.isfinite(sigma):
            sigma = 1.0

        price_confidence = 1.0 / (1.0 + 8.0 * sigma)
        confidence = self._clip(
            0.70 * price_confidence
            + 0.20 * hazard_confidence
            + 0.10 * seller.success_prob,
            0.0,
            1.0,
        )

        return PredictiveDistribution(
            fair_value=fair,
            acquisition_cost=acquisition,
            fair_value_net_roi=baseline_roi,
            expected_exit_net=expected_exit_net,
            expected_net_roi=expected_roi,
            sigma_net_roi=sigma,
            expected_holding_days=expected_days,
            sale_prob_30d=sale_prob_30d,
            seller_success_prob=seller.success_prob,
            condition_risk=condition.risk,
            regime_weight=regime.weight,
            confidence=confidence,
            factor_net_roi=factor_roi,
            anomaly_net_roi=anomaly_roi,
            locked_net_roi=locked_roi,
        )

    def score(self, c: dict) -> StackScore:
        prediction = self.predict(c)
        if prediction is None:
            buy = self._f(c, "buy_price")
            if buy <= 0:
                return self._empty("invalid_buy_price")
            acquisition = (
                buy * (1.0 + self._f(c, "buy_fee_rate"))
                + self._f(c, "buy_fixed")
                + self._f(c, "buy_shipping")
                + self._f(c, "buy_tax")
            )
            return self._empty("no_fair_value", acquisition)

        lcb = (
            prediction.expected_net_roi
            - self.lcb_z * prediction.sigma_net_roi
        )
        score = lcb / max(prediction.expected_holding_days, 1.0)
        seller_ok = prediction.seller_success_prob >= 0.45
        condition_ok = prediction.condition_risk <= 0.65
        finite = math.isfinite(lcb) and math.isfinite(score)
        trade = bool(
            finite
            and lcb > self.min_lcb_roi
            and seller_ok
            and condition_ok
        )

        if not seller_ok:
            reason = "seller_quality_gate"
        elif not condition_ok:
            reason = "condition_risk_gate"
        elif not finite:
            reason = "non_finite_prediction"
        elif lcb <= self.min_lcb_roi:
            reason = "unified_lcb_gate"
        elif prediction.locked_net_roi is not None:
            reason = "locked_exit_unified_lcb"
        else:
            reason = "unified_predictive_lcb"

        return StackScore(
            trade=trade,
            fair_value=prediction.fair_value,
            acquisition_cost=prediction.acquisition_cost,
            expected_exit_net=prediction.expected_exit_net,
            fair_value_net_roi=prediction.fair_value_net_roi,
            factor_net_roi=prediction.factor_net_roi,
            anomaly_net_roi=prediction.anomaly_net_roi,
            locked_net_roi=prediction.locked_net_roi,
            expected_holding_days=prediction.expected_holding_days,
            sale_prob_30d=prediction.sale_prob_30d,
            seller_success_prob=prediction.seller_success_prob,
            condition_risk=prediction.condition_risk,
            regime_weight=prediction.regime_weight,
            ensemble_confidence=prediction.confidence,
            conservative_net_roi=lcb,
            lcb_net_roi=lcb,
            score_per_capital_day=score,
            reason=reason,
        )

    @staticmethod
    def _empty(reason: str, acquisition: float = 0.0) -> StackScore:
        return StackScore(
            trade=False,
            fair_value=0.0,
            acquisition_cost=acquisition,
            expected_exit_net=0.0,
            fair_value_net_roi=0.0,
            factor_net_roi=None,
            anomaly_net_roi=None,
            locked_net_roi=None,
            expected_holding_days=365.0,
            sale_prob_30d=0.0,
            seller_success_prob=0.5,
            condition_risk=1.0,
            regime_weight=0.2,
            ensemble_confidence=0.0,
            conservative_net_roi=-1.0,
            lcb_net_roi=-1.0,
            score_per_capital_day=-1.0,
            reason=reason,
        )
