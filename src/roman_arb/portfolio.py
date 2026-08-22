from __future__ import annotations
from collections import defaultdict
from .models import Opportunity, Position, Trade


class Portfolio:
    def __init__(self, initial_capital: float, assumptions: dict):
        self.initial_capital = float(initial_capital)
        self.cash = float(initial_capital)
        self.positions: list[Position] = []
        self.trades: list[Trade] = []
        self.a = assumptions
        self.capital_days = 0.0
        self.utilization_sum = 0.0
        self.equity_history: list[dict] = []
        self.rejected_capital = 0

    @property
    def invested(self) -> float:
        return sum(p.acquisition_cost for p in self.positions)

    @property
    def utilization(self) -> float:
        denom = max(self.initial_capital, 1e-9)
        return min(1.0, self.invested / denom)

    def sector_invested(self, sector: str) -> float:
        return sum(p.acquisition_cost for p in self.positions if p.sector == sector)

    def can_open(self, opp: Opportunity) -> bool:
        cost = opp.listing.acquisition_cost
        if cost > self.initial_capital * float(self.a["max_item_fraction"]):
            return False
        if self.sector_invested(opp.listing.sector) + cost > self.initial_capital * float(self.a["max_sector_fraction"]):
            return False
        reserve = self.initial_capital * float(self.a["cash_buffer_fraction"])
        return self.cash - cost >= reserve

    def open_position(self, position: Position) -> bool:
        if self.cash < position.acquisition_cost:
            self.rejected_capital += 1
            return False
        self.cash -= position.acquisition_cost
        self.positions.append(position)
        return True

    def close_position(self, position: Position, trade: Trade):
        self.cash += trade.proceeds
        self.positions.remove(position)
        self.trades.append(trade)

    def mark_day(self, day: int):
        self.capital_days += self.invested
        realized_equity = self.cash + sum(p.acquisition_cost for p in self.positions)
        deployed_fraction = self.invested / max(realized_equity, 1e-9)
        self.utilization_sum += deployed_fraction
        self.equity_history.append({
            "day": day, "cash": self.cash, "invested_cost": self.invested,
            "realized_cost_equity": realized_equity, "deployed_fraction": deployed_fraction,
            "open_positions": len(self.positions)
        })
