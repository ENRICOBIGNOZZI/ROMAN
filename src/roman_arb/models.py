from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Venue:
    key: str
    sell_fee: float
    fixed_exit: float = 0.0
    price_haircut: float = 0.0


@dataclass(frozen=True)
class Sector:
    key: str
    name: str
    candidate_rate: float
    avg_ticket: float
    ticket_sigma: float
    gross_discount_mu: float
    gross_discount_sigma: float
    model_sigma: float
    holding_days: float
    holding_sigma: float
    fill_prob: float
    quality_sigma: float
    problem_prob: float
    problem_loss: float
    buy_cost_pct: float
    buy_fixed: float
    exit_venues: tuple[str, ...]
    source_venues: tuple[str, ...] = ()
    family: str = ""
    buy_venues: tuple[str, ...] = ()


@dataclass
class Listing:
    listing_id: str
    day: int
    sector: str
    buy_venue: str
    buy_price: float
    true_fair_value: float
    estimated_fair_value: float
    model_sigma: float
    expected_holding_days: float
    fill_prob: float
    quality_sigma: float
    problem_prob: float
    problem_loss: float
    buy_cost_pct: float
    buy_fixed: float
    exit_venues: tuple[str, ...]

    @property
    def acquisition_cost(self) -> float:
        return self.buy_price * (1.0 + self.buy_cost_pct) + self.buy_fixed


@dataclass
class Opportunity:
    listing: Listing
    exit_venue: str
    estimated_net_proceeds: float
    estimated_profit: float
    lcb_profit: float
    lcb_roi: float
    score: float


@dataclass
class Position:
    opportunity: Opportunity
    entry_day: int
    planned_exit_day: int
    acquisition_cost: float
    true_exit_value_at_entry: float
    sector: str


@dataclass
class Trade:
    listing_id: str
    sector: str
    buy_venue: str
    exit_venue: str
    entry_day: int
    exit_day: int
    holding_days: int
    acquisition_cost: float
    proceeds: float
    pnl: float
    roi: float
    forced: bool = False
    problem: bool = False
