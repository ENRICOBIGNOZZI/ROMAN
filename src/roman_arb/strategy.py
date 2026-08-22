from __future__ import annotations
import numpy as np
from .fees import FeeEngine
from .models import Listing, Opportunity


class Strategy:
    def __init__(self, fee_engine: FeeEngine, assumptions: dict, rng: np.random.Generator):
        self.fees = fee_engine
        self.a = assumptions
        self.rng = rng

    def _venue_fair_values(self, listing: Listing) -> dict[str, float]:
        # Small venue basis; unknown exact executable price is handled later by execution noise.
        out = {}
        for v in listing.exit_venues:
            basis = self.rng.normal(0.0, 0.008)
            out[v] = listing.estimated_fair_value * (1.0 + basis)
        return out

    def evaluate(self, listing: Listing, utilization: float) -> Opportunity | None:
        by_venue = self._venue_fair_values(listing)
        est_net, exit_venue = self.fees.best_exit(by_venue, listing.exit_venues)
        acquisition = listing.acquisition_cost
        est_profit = est_net - acquisition

        # Approximate monetary uncertainty: fair-value model + quality component.
        sigma_money = listing.estimated_fair_value * np.sqrt(
            listing.model_sigma**2 + listing.quality_sigma**2 + 0.006**2
        )
        lcb_profit = est_profit - float(self.a["lcb_z"]) * sigma_money
        lcb_roi = lcb_profit / max(acquisition, 1e-9)
        score = lcb_profit / max(acquisition * listing.expected_holding_days, 1e-9)

        hurdle = (
            float(self.a["shadow_hurdle_base_daily"])
            + float(self.a["shadow_hurdle_slope_daily"]) * utilization**2
        )
        if lcb_roi < float(self.a["min_lcb_roi"]) or score < hurdle:
            return None
        return Opportunity(
            listing=listing, exit_venue=exit_venue,
            estimated_net_proceeds=est_net, estimated_profit=est_profit,
            lcb_profit=lcb_profit, lcb_roi=lcb_roi, score=score,
        )
