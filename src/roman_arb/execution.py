from __future__ import annotations
import math
import numpy as np
from .fees import FeeEngine
from .models import Opportunity, Position, Trade


class ExecutionModel:
    def __init__(self, fees: FeeEngine, sectors, assumptions: dict, rng: np.random.Generator):
        self.fees = fees
        self.sectors = sectors
        self.a = assumptions
        self.rng = rng

    def try_fill(self, opp: Opportunity, day: int) -> Position | None:
        l = opp.listing
        if self.rng.random() > l.fill_prob:
            return None
        s = self.sectors[l.sector]
        hold = max(1, int(round(s.holding_days * math.exp(self.rng.normal(-0.5*s.holding_sigma**2, s.holding_sigma)))))
        hold = min(hold, int(self.a["forced_liquidation_days"]))
        return Position(
            opportunity=opp, entry_day=day, planned_exit_day=day+hold,
            acquisition_cost=l.acquisition_cost,
            true_exit_value_at_entry=l.true_fair_value,
            sector=l.sector,
        )

    def close(self, pos: Position, day: int, forced: bool = False) -> Trade:
        l = pos.opportunity.listing
        s = self.sectors[l.sector]
        hold = max(1, day - pos.entry_day)
        # Market drift/noise over holding period; centered conservatively slightly negative.
        market_noise = self.rng.normal(-0.00004 * hold, 0.0045 * np.sqrt(hold))
        quality_haircut = abs(self.rng.normal(0.0, l.quality_sigma))
        gross = pos.true_exit_value_at_entry * math.exp(market_noise) * (1.0 - quality_haircut)
        if forced:
            gross *= 0.965
        problem = bool(self.rng.random() < l.problem_prob)
        if problem:
            gross *= (1.0 - l.problem_loss)
        proceeds = self.fees.net_proceeds(gross, pos.opportunity.exit_venue)
        pnl = proceeds - pos.acquisition_cost
        return Trade(
            listing_id=l.listing_id, sector=l.sector, buy_venue=l.buy_venue,
            exit_venue=pos.opportunity.exit_venue, entry_day=pos.entry_day,
            exit_day=day, holding_days=hold, acquisition_cost=pos.acquisition_cost,
            proceeds=proceeds, pnl=pnl, roi=pnl/max(pos.acquisition_cost, 1e-9),
            forced=forced, problem=problem,
        )
