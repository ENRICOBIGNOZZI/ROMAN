from __future__ import annotations
import math
import numpy as np
from .models import Listing, Sector


BUY_VENUES = (
    "local", "ebay", "stockx", "goat", "chrono24", "bricklink",
    "tcgplayer", "reverb", "whatnot"
)


class SyntheticMarketStream:
    """Generates candidate listings, not the entire raw marketplace firehose."""

    def __init__(self, sectors: dict[str, Sector], rng: np.random.Generator, assumptions: dict, arrival_multiplier: float | None = None, edge_shrinkage: float | None = None):
        self.sectors = sectors
        self.rng = rng
        self.a = assumptions
        self.arrival_multiplier = float(arrival_multiplier if arrival_multiplier is not None else assumptions.get("arrival_multiplier", 1.0))
        self.edge_shrinkage = float(edge_shrinkage if edge_shrinkage is not None else assumptions.get("edge_shrinkage", 0.60))
        self.counter = 0

    def _ticket(self, s: Sector) -> float:
        # lognormal parameterized approximately by median = avg_ticket
        return float(np.clip(s.avg_ticket * np.exp(self.rng.normal(0, s.ticket_sigma)), 25, 12000))

    def _listing(self, day: int, s: Sector) -> Listing:
        self.counter += 1
        buy_price = self._ticket(s)
        # Candidate prefilter: some "discounts" are real, some are noise/quality.
        apparent_discount = float(np.clip(
            self.rng.normal(s.gross_discount_mu, s.gross_discount_sigma), -0.03, 0.40
        ))
        # Selection/winner's curse: a listing that *looks* 15% cheap is usually not
        # truly 15% cheap once hidden condition, stale comps and seller/venue effects
        # are resolved. Only part of the apparent dislocation survives out of sample.
        shrink = self.edge_shrinkage
        hidden = self.rng.normal(float(self.a.get("edge_hidden_mean", -0.003)), float(self.a.get("edge_hidden_sigma_base", 0.008)) + 0.20 * s.model_sigma)
        true_discount = float(np.clip(shrink * apparent_discount + hidden, -0.08, 0.24))
        true_fair = buy_price / max(0.70, 1.0 - true_discount)
        expected_discount = float(np.clip(shrink * apparent_discount - 0.003, -0.05, 0.22))
        expected_fair = buy_price / max(0.72, 1.0 - expected_discount)
        # The strategy has learned the shrinkage, but still has model error.
        est_error = self.rng.normal(0.0, 0.55 * s.model_sigma)
        estimated_fair = expected_fair * math.exp(est_error)
        buy_venue = str(self.rng.choice(BUY_VENUES))
        return Listing(
            listing_id=f"L{self.counter:09d}", day=day, sector=s.key,
            buy_venue=buy_venue, buy_price=buy_price,
            true_fair_value=true_fair, estimated_fair_value=estimated_fair,
            model_sigma=s.model_sigma,
            expected_holding_days=s.holding_days,
            fill_prob=s.fill_prob,
            quality_sigma=s.quality_sigma,
            problem_prob=s.problem_prob,
            problem_loss=s.problem_loss,
            buy_cost_pct=s.buy_cost_pct,
            buy_fixed=s.buy_fixed,
            exit_venues=s.exit_venues,
        )

    def events_for_day(self, day: int) -> list[Listing]:
        events = []
        for s in self.sectors.values():
            n = int(self.rng.poisson(s.candidate_rate * self.arrival_multiplier))
            events.extend(self._listing(day, s) for _ in range(n))
        self.rng.shuffle(events)
        return events
