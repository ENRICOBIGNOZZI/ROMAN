from __future__ import annotations
from .models import Venue


class FeeEngine:
    def __init__(self, venues: dict[str, Venue]):
        self.venues = venues

    def net_proceeds(self, gross_price: float, venue_key: str) -> float:
        v = self.venues[venue_key]
        effective_price = gross_price * (1.0 - v.price_haircut)
        return effective_price * (1.0 - v.sell_fee) - v.fixed_exit

    def best_exit(self, gross_price_by_venue: dict[str, float], allowed: tuple[str, ...]):
        candidates = []
        for venue in allowed:
            if venue not in gross_price_by_venue or venue not in self.venues:
                continue
            proceeds = self.net_proceeds(gross_price_by_venue[venue], venue)
            candidates.append((proceeds, venue))
        if not candidates:
            raise ValueError("No valid exit venue")
        return max(candidates)
