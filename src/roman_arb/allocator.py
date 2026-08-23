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
    """Simple greedy allocator targeting LCB net profit per capital-day.

    The allocator intentionally does *not* try to maximize utilization. A locked
    executable arbitrage may use more capital than an inventory/model trade.
    """

    def __init__(
        self,
        capital: float = 10_000.0,
        cash_buffer_fraction: float = 0.10,
        max_inventory_item_fraction: float = 0.30,
        max_locked_item_fraction: float = 0.45,
        max_sector_fraction: float = 0.45,
        max_source_fraction: float = 0.55,
        max_positions: int = 30,
    ):
        self.capital = float(capital)
        self.cash_buffer_fraction = float(cash_buffer_fraction)
        self.max_inventory_item_fraction = float(max_inventory_item_fraction)
        self.max_locked_item_fraction = float(max_locked_item_fraction)
        self.max_sector_fraction = float(max_sector_fraction)
        self.max_source_fraction = float(max_source_fraction)
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

        for p in existing:
            cost = max(0.0, self._f(p, "acquisition_cost"))
            used += cost
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

        def utility(c: dict) -> tuple[float, float, float]:
            score = self._f(c, "score_per_capital_day", -1e9)
            roi = self._f(c, "lcb_net_roi", -1e9)
            cost = max(self._f(c, "acquisition_cost"), 1e-9)
            # Tie-break toward higher absolute daily LCB PnL, then higher ROI.
            return score, score * cost, roi

        for c in sorted(candidates, key=utility, reverse=True):
            if len(existing) + len(selected) >= self.max_positions:
                break
            if not bool(c.get("trade", True)):
                continue
            cost = self._f(c, "acquisition_cost")
            if cost <= 0 or cost > available:
                continue
            locked = bool(c.get("locked") or c.get("locked_net_roi") is not None)
            item_cap = self.capital * (self.max_locked_item_fraction if locked else self.max_inventory_item_fraction)
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
            lcb_roi = self._f(c, "lcb_net_roi", -1.0)
            days = max(self._f(c, "expected_holding_days", 365.0), 1.0)
            if lcb_roi <= 0:
                continue

            selected.append(c)
            available -= cost
            used += cost
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
