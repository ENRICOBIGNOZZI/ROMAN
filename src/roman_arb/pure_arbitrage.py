from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class ArbitrageLeg:
    venue: str
    side: str  # "buy" or "sell"
    executable_price: float
    fee_rate: float = 0.0
    fixed_fee: float = 0.0
    shipping: float = 0.0
    tax: float = 0.0
    authentication: float = 0.0
    fx_cost: float = 0.0
    other_cost: float = 0.0
    available_qty: float = 1.0
    fill_prob: float = 1.0
    latency_ms: float = 0.0
    stale_ms: float = 0.0
    route_risk: float = 0.0

    def __post_init__(self) -> None:
        if self.side not in {"buy", "sell"}:
            raise ValueError("side must be 'buy' or 'sell'")
        if self.executable_price <= 0 or not math.isfinite(self.executable_price):
            raise ValueError("executable_price must be finite and positive")
        if self.available_qty <= 0 or not math.isfinite(self.available_qty):
            raise ValueError("available_qty must be finite and positive")

    @property
    def all_fixed_costs(self) -> float:
        return (
            self.fixed_fee
            + self.shipping
            + self.tax
            + self.authentication
            + self.fx_cost
            + self.other_cost
        )

    def buy_cost(self, qty: float = 1.0) -> float:
        if self.side != "buy":
            raise ValueError("buy_cost called on non-buy leg")
        return qty * self.executable_price * (1.0 + self.fee_rate) + self.all_fixed_costs

    def sell_proceeds(self, qty: float = 1.0) -> float:
        if self.side != "sell":
            raise ValueError("sell_proceeds called on non-sell leg")
        return qty * self.executable_price * (1.0 - self.fee_rate) - self.all_fixed_costs


@dataclass(frozen=True)
class PureArbitrageOpportunity:
    entity_key: str
    buy_leg: ArbitrageLeg
    sell_leg: ArbitrageLeg
    quantity: float
    acquisition_cost: float
    locked_exit_net: float
    locked_profit: float
    locked_net_roi: float
    success_prob: float
    expected_profit: float
    downside_if_second_leg_fails: float
    leg_risk_penalty: float
    conservative_profit: float
    conservative_net_roi: float
    score_per_capital_day: float
    executable: bool
    reason: str


class PureArbitrageEngine:
    """Find genuinely executable cross-venue cash-and-carry resale arbitrage.

    The engine deliberately does *not* use fair-value forecasts.  A candidate
    exists only when there is an executable buy price and executable sell bid
    for the same normalized entity.  All explicit costs are applied to both
    legs before declaring an arbitrage.

    Since physical resale legs are not atomic, the raw locked spread is further
    discounted by fill probability, latency/staleness and route/leg risk.
    """

    def __init__(
        self,
        *,
        min_locked_roi: float = 0.003,
        min_conservative_roi: float = 0.001,
        min_success_prob: float = 0.75,
        max_stale_ms: float = 30_000.0,
        max_latency_ms: float = 10_000.0,
        failure_loss_fraction: float = 0.06,
        default_capital_days: float = 1.0,
    ) -> None:
        self.min_locked_roi = float(min_locked_roi)
        self.min_conservative_roi = float(min_conservative_roi)
        self.min_success_prob = float(min_success_prob)
        self.max_stale_ms = float(max_stale_ms)
        self.max_latency_ms = float(max_latency_ms)
        self.failure_loss_fraction = float(failure_loss_fraction)
        self.default_capital_days = max(float(default_capital_days), 1e-9)

    @staticmethod
    def _clip01(x: float) -> float:
        return max(0.0, min(1.0, float(x)))

    def _execution_success_prob(self, buy: ArbitrageLeg, sell: ArbitrageLeg) -> float:
        p = self._clip01(buy.fill_prob) * self._clip01(sell.fill_prob)

        # Smoothly reduce confidence as quotes get old or execution becomes slow.
        if self.max_stale_ms > 0:
            p *= math.exp(-max(buy.stale_ms, sell.stale_ms, 0.0) / self.max_stale_ms)
        if self.max_latency_ms > 0:
            p *= math.exp(-(max(buy.latency_ms, 0.0) + max(sell.latency_ms, 0.0)) / self.max_latency_ms)

        route_survival = (1.0 - self._clip01(buy.route_risk)) * (1.0 - self._clip01(sell.route_risk))
        return self._clip01(p * route_survival)

    def evaluate_pair(
        self,
        *,
        entity_key: str,
        buy_leg: ArbitrageLeg,
        sell_leg: ArbitrageLeg,
        quantity: float | None = None,
        capital_days: float | None = None,
    ) -> PureArbitrageOpportunity:
        if buy_leg.side != "buy" or sell_leg.side != "sell":
            raise ValueError("evaluate_pair requires buy_leg.side='buy' and sell_leg.side='sell'")
        if buy_leg.venue == sell_leg.venue:
            return self._rejected(entity_key, buy_leg, sell_leg, "same_venue")

        qty = min(buy_leg.available_qty, sell_leg.available_qty)
        if quantity is not None:
            qty = min(qty, max(float(quantity), 0.0))
        if qty <= 0:
            return self._rejected(entity_key, buy_leg, sell_leg, "zero_executable_quantity")

        acquisition = buy_leg.buy_cost(qty)
        exit_net = sell_leg.sell_proceeds(qty)
        profit = exit_net - acquisition
        roi = profit / max(acquisition, 1e-12)

        p_success = self._execution_success_prob(buy_leg, sell_leg)
        fail_loss = self.failure_loss_fraction * acquisition
        expected_profit = p_success * profit - (1.0 - p_success) * fail_loss

        # Extra model-free penalty for non-atomic physical execution. Route risk
        # is already in p_success; the penalty keeps borderline spreads out.
        leg_risk_penalty = (1.0 - p_success) * fail_loss
        conservative_profit = profit - leg_risk_penalty
        conservative_roi = conservative_profit / max(acquisition, 1e-12)

        days = max(float(capital_days or self.default_capital_days), 1e-9)
        score = conservative_roi / days

        fresh = max(buy_leg.stale_ms, sell_leg.stale_ms) <= self.max_stale_ms
        fast = buy_leg.latency_ms <= self.max_latency_ms and sell_leg.latency_ms <= self.max_latency_ms
        executable = (
            profit > 0
            and roi >= self.min_locked_roi
            and conservative_roi >= self.min_conservative_roi
            and p_success >= self.min_success_prob
            and fresh
            and fast
        )

        reason = "pure_locked_arbitrage" if executable else self._reason(
            profit=profit,
            roi=roi,
            conservative_roi=conservative_roi,
            p_success=p_success,
            fresh=fresh,
            fast=fast,
        )

        return PureArbitrageOpportunity(
            entity_key=str(entity_key),
            buy_leg=buy_leg,
            sell_leg=sell_leg,
            quantity=qty,
            acquisition_cost=acquisition,
            locked_exit_net=exit_net,
            locked_profit=profit,
            locked_net_roi=roi,
            success_prob=p_success,
            expected_profit=expected_profit,
            downside_if_second_leg_fails=fail_loss,
            leg_risk_penalty=leg_risk_penalty,
            conservative_profit=conservative_profit,
            conservative_net_roi=conservative_roi,
            score_per_capital_day=score,
            executable=executable,
            reason=reason,
        )

    def scan_entity(
        self,
        entity_key: str,
        buy_legs: Sequence[ArbitrageLeg],
        sell_legs: Sequence[ArbitrageLeg],
        *,
        capital_days: float | None = None,
    ) -> list[PureArbitrageOpportunity]:
        out: list[PureArbitrageOpportunity] = []
        for buy in buy_legs:
            if buy.side != "buy":
                continue
            for sell in sell_legs:
                if sell.side != "sell" or buy.venue == sell.venue:
                    continue
                opp = self.evaluate_pair(
                    entity_key=entity_key,
                    buy_leg=buy,
                    sell_leg=sell,
                    capital_days=capital_days,
                )
                if opp.executable:
                    out.append(opp)
        return sorted(out, key=lambda x: (x.score_per_capital_day, x.conservative_profit), reverse=True)

    def scan_market(
        self,
        books: Mapping[str, Mapping[str, Sequence[ArbitrageLeg]]],
        *,
        capital_days: float | None = None,
    ) -> list[PureArbitrageOpportunity]:
        """Scan normalized entity books.

        Expected shape::

            {
                "entity-key": {
                    "buys": [ArbitrageLeg(..., side="buy")],
                    "sells": [ArbitrageLeg(..., side="sell")],
                }
            }
        """
        out: list[PureArbitrageOpportunity] = []
        for entity_key, book in books.items():
            out.extend(
                self.scan_entity(
                    entity_key,
                    list(book.get("buys", ())),
                    list(book.get("sells", ())),
                    capital_days=capital_days,
                )
            )
        return sorted(out, key=lambda x: (x.score_per_capital_day, x.conservative_profit), reverse=True)

    def best(self, books: Mapping[str, Mapping[str, Sequence[ArbitrageLeg]]]) -> PureArbitrageOpportunity | None:
        opps = self.scan_market(books)
        return opps[0] if opps else None

    def _reason(
        self,
        *,
        profit: float,
        roi: float,
        conservative_roi: float,
        p_success: float,
        fresh: bool,
        fast: bool,
    ) -> str:
        if profit <= 0:
            return "negative_net_spread"
        if roi < self.min_locked_roi:
            return "locked_roi_below_threshold"
        if conservative_roi < self.min_conservative_roi:
            return "leg_risk_erases_edge"
        if p_success < self.min_success_prob:
            return "execution_probability_too_low"
        if not fresh:
            return "stale_quote"
        if not fast:
            return "execution_latency_too_high"
        return "rejected"

    @staticmethod
    def _rejected(entity_key: str, buy_leg: ArbitrageLeg, sell_leg: ArbitrageLeg, reason: str) -> PureArbitrageOpportunity:
        return PureArbitrageOpportunity(
            entity_key=str(entity_key),
            buy_leg=buy_leg,
            sell_leg=sell_leg,
            quantity=0.0,
            acquisition_cost=0.0,
            locked_exit_net=0.0,
            locked_profit=0.0,
            locked_net_roi=0.0,
            success_prob=0.0,
            expected_profit=0.0,
            downside_if_second_leg_fails=0.0,
            leg_risk_penalty=0.0,
            conservative_profit=0.0,
            conservative_net_roi=0.0,
            score_per_capital_day=0.0,
            executable=False,
            reason=reason,
        )
