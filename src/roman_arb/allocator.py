from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AllocationResult:
    selected: tuple[dict, ...]
    capital_used: float
    capital_remaining: float
    expected_lcb_profit: float
    expected_lcb_profit_per_day: float


class CapitalDayAllocator:
    """Liquidity-first allocator for a small-capital resale book.

    Objective: high *net LCB profit per capital-day*, not maximum utilization.
    Slow inventory receives explicit bucket constraints so EUR 10k cannot become
    trapped in attractive-looking but hard-to-exit objects.
    """

    def __init__(
        self,
        capital: float = 10_000.0,
        cash_buffer_fraction: float = 0.20,
        max_inventory_item_fraction: float = 0.25,
        max_locked_item_fraction: float = 0.40,
        max_sector_fraction: float = 0.40,
        max_source_fraction: float = 0.50,
        max_medium_inventory_fraction: float = 0.45,
        max_slow_inventory_fraction: float = 0.20,
        medium_days: float = 14.0,
        slow_days: float = 21.0,
        hard_max_inventory_days: float = 45.0,
        min_inventory_score_per_day: float = 0.00035,
        min_locked_score_per_day: float = 0.00015,
        min_sale_prob_30d: float = 0.55,
        max_positions: int = 24,
    ):
        self.capital = float(capital)
        self.cash_buffer_fraction = float(cash_buffer_fraction)
        self.max_inventory_item_fraction = float(max_inventory_item_fraction)
        self.max_locked_item_fraction = float(max_locked_item_fraction)
        self.max_sector_fraction = float(max_sector_fraction)
        self.max_source_fraction = float(max_source_fraction)
        self.max_medium_inventory_fraction = float(max_medium_inventory_fraction)
        self.max_slow_inventory_fraction = float(max_slow_inventory_fraction)
        self.medium_days = float(medium_days)
        self.slow_days = float(slow_days)
        self.hard_max_inventory_days = float(hard_max_inventory_days)
        self.min_inventory_score_per_day = float(min_inventory_score_per_day)
        self.min_locked_score_per_day = float(min_locked_score_per_day)
        self.min_sale_prob_30d = float(min_sale_prob_30d)
        self.max_positions = int(max_positions)

    @staticmethod
    def _f(c: dict, key: str, default: float = 0.0) -> float:
        try:
            return float(c.get(key, default))
        except Exception:
            return float(default)

    def allocate(self, candidates: list[dict], existing: list[dict] | None = None) -> AllocationResult:
        existing = list(existing or [])
        reserve = self.capital * self.cash_buffer_fraction
        sector_used: dict[str, float] = {}
        source_used: dict[str, float] = {}
        entity_keys = set()
        used = 0.0
        medium_used = 0.0
        slow_used = 0.0

        for p in existing:
            cost = max(0.0, self._f(p, "acquisition_cost"))
            used += cost
            days = max(1.0, self._f(p, "expected_days", self._f(p, "expected_holding_days", 365.0)))
            if days > self.medium_days:
                medium_used += cost
            if days > self.slow_days:
                slow_used += cost
            sector = str(p.get("sector") or "unknown")
            source = str(p.get("buy_source") or p.get("buy_venue") or "unknown")
            sector_used[sector] = sector_used.get(sector, 0.0) + cost
            source_used[source] = source_used.get(source, 0.0) + cost
            if p.get("entity_key"):
                entity_keys.add(str(p["entity_key"]))

        available = max(0.0, self.capital - reserve - used)
        selected: list[dict] = []
        total_lcb = 0.0
        total_daily = 0.0

        def utility(c: dict) -> tuple[float, float, float, float]:
            score = self._f(c, "score_per_capital_day", -1e9)
            roi = self._f(c, "lcb_net_roi", -1e9)
            cost = max(self._f(c, "acquisition_cost"), 1e-9)
            sale = self._f(c, "sale_prob_30d", 0.0)
            # Liquidity is a tie-breaker after capital-day economics.
            return score, score * cost, sale, roi

        for c in sorted(candidates, key=utility, reverse=True):
            if len(existing) + len(selected) >= self.max_positions:
                break
            if not bool(c.get("trade", True)):
                continue
            cost = self._f(c, "acquisition_cost")
            if cost <= 0 or cost > available:
                continue
            locked = bool(c.get("locked") or c.get("locked_net_roi") is not None)
            days = max(self._f(c, "expected_holding_days", 365.0), 1.0)
            score = self._f(c, "score_per_capital_day", -1e9)
            sale30 = self._f(c, "sale_prob_30d", 0.0)

            # A locked/fresh executable exit is a different economic object from
            # an inventory bet. Inventory must recycle capital reasonably fast.
            if locked:
                if score < self.min_locked_score_per_day:
                    continue
            else:
                if score < self.min_inventory_score_per_day:
                    continue
                if days > self.hard_max_inventory_days:
                    continue
                if sale30 < self.min_sale_prob_30d:
                    continue

            item_cap = self.capital * (
                self.max_locked_item_fraction if locked else self.max_inventory_item_fraction
            )
            if cost > item_cap:
                continue

            entity = str(c.get("entity_key") or "")
            if entity and entity in entity_keys:
                continue
            sector = str(c.get("sector") or "unknown")
            source = str(c.get("buy_source") or c.get("buy_venue") or "unknown")
            if sector_used.get(sector, 0.0) + cost > self.capital * self.max_sector_fraction:
                continue
            if source_used.get(source, 0.0) + cost > self.capital * self.max_source_fraction:
                continue

            # Explicit maturity buckets. At most 45% of total capital can have an
            # expected hold >14d, and only 20% can have expected hold >21d.
            if days > self.medium_days and medium_used + cost > self.capital * self.max_medium_inventory_fraction:
                continue
            if days > self.slow_days and slow_used + cost > self.capital * self.max_slow_inventory_fraction:
                continue

            lcb_roi = self._f(c, "lcb_net_roi", -1.0)
            if lcb_roi <= 0:
                continue

            selected.append(c)
            available -= cost
            used += cost
            if days > self.medium_days:
                medium_used += cost
            if days > self.slow_days:
                slow_used += cost
            sector_used[sector] = sector_used.get(sector, 0.0) + cost
            source_used[source] = source_used.get(source, 0.0) + cost
            if entity:
                entity_keys.add(entity)
            lcb_profit = cost * lcb_roi
            total_lcb += lcb_profit
            total_daily += lcb_profit / days

        return AllocationResult(
            selected=tuple(selected),
            capital_used=used,
            capital_remaining=max(0.0, self.capital - used),
            expected_lcb_profit=total_lcb,
            expected_lcb_profit_per_day=total_daily,
        )
