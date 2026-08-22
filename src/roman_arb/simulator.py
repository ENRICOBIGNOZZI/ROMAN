from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
import numpy as np
import pandas as pd
from .config import load_config
from .fees import FeeEngine
from .stream import SyntheticMarketStream
from .strategy import Strategy
from .portfolio import Portfolio
from .execution import ExecutionModel
from .metrics import summarize, trades_frame, sector_frame


@dataclass
class SimulationResult:
    summary: dict
    trades: pd.DataFrame
    sectors: pd.DataFrame
    equity: pd.DataFrame


class PaperEngine:
    """Stateful event-driven paper-trading engine.

    One `step(day)` advances the same cash/inventory state. This lets the same
    core drive accelerated simulations, a live-like console, or future real
    adapters without liquidating inventory between ticks.
    """

    def __init__(self, initial_capital=20_000.0, seed=7, config_path=None,
                 arrival_multiplier=None, edge_shrinkage=None):
        assumptions, venues, sectors = load_config(config_path)
        self.assumptions = assumptions
        self.venues = venues
        self.sectors = sectors
        self.initial_capital = float(initial_capital)
        self.rng = np.random.default_rng(seed)
        self.fees = FeeEngine(venues)
        self.stream = SyntheticMarketStream(
            sectors, self.rng, assumptions,
            arrival_multiplier=arrival_multiplier,
            edge_shrinkage=edge_shrinkage,
        )
        self.strategy = Strategy(self.fees, assumptions, self.rng)
        self.portfolio = Portfolio(initial_capital, assumptions)
        self.execution = ExecutionModel(self.fees, sectors, assumptions, self.rng)
        self.candidate_count = 0
        self.evaluated_count = 0
        self.filled_count = 0
        self.seed = seed
        self.arrival_multiplier = float(arrival_multiplier if arrival_multiplier is not None else assumptions.get("arrival_multiplier", 1.0))
        self.edge_shrinkage = float(edge_shrinkage if edge_shrinkage is not None else assumptions.get("edge_shrinkage", 0.60))
        self.last_day = -1

    def step(self, day: int) -> dict:
        if day <= self.last_day:
            raise ValueError("day must increase monotonically")
        self.last_day = day

        # 1) Realize exits first so released cash can fund today's arrivals.
        closed_today = 0
        for pos in list(self.portfolio.positions):
            if day >= pos.planned_exit_day:
                forced = (day - pos.entry_day) >= int(self.assumptions["forced_liquidation_days"])
                trade = self.execution.close(pos, day, forced=forced)
                self.portfolio.close_position(pos, trade)
                closed_today += 1

        # 2) Ingest candidate listing events.
        events = self.stream.events_for_day(day)
        self.candidate_count += len(events)

        # 3) Score first, then spend scarce capital on the best same-day candidates.
        opps = []
        for listing in events:
            opp = self.strategy.evaluate(listing, self.portfolio.utilization)
            if opp is not None:
                self.evaluated_count += 1
                opps.append(opp)
        opps.sort(key=lambda x: x.score, reverse=True)

        opened_today = 0
        for opp in opps:
            if not self.portfolio.can_open(opp):
                self.portfolio.rejected_capital += 1
                continue
            pos = self.execution.try_fill(opp, day)
            if pos is not None and self.portfolio.open_position(pos):
                self.filled_count += 1
                opened_today += 1

        self.portfolio.mark_day(day)
        return {
            "day": day,
            "cash": self.portfolio.cash,
            "invested": self.portfolio.invested,
            "open_positions": len(self.portfolio.positions),
            "trades_total": len(self.portfolio.trades),
            "candidates_today": len(events),
            "qualified_today": len(opps),
            "opened_today": opened_today,
            "closed_today": closed_today,
            "utilization": self.portfolio.utilization,
        }

    def liquidate(self, day: int):
        for pos in list(self.portfolio.positions):
            trade = self.execution.close(pos, day, forced=True)
            self.portfolio.close_position(pos, trade)

    def result(self, days: int, liquidate=True) -> SimulationResult:
        if liquidate and self.portfolio.positions:
            self.liquidate(max(days, self.last_day + 1))
        summary = summarize(
            self.initial_capital, self.portfolio.cash, self.portfolio.positions,
            self.portfolio.trades, self.portfolio.capital_days,
            self.portfolio.utilization_sum, max(days, 1)
        )
        summary.update({
            "candidate_listings": self.candidate_count,
            "strategy_qualified": self.evaluated_count,
            "fills": self.filled_count,
            "rejected_for_capital_or_limits": self.portfolio.rejected_capital,
            "seed": self.seed,
            "days": days,
            "arrival_multiplier": self.arrival_multiplier,
            "edge_shrinkage": self.edge_shrinkage,
        })
        return SimulationResult(
            summary=summary,
            trades=trades_frame(self.portfolio.trades),
            sectors=sector_frame(self.portfolio.trades),
            equity=pd.DataFrame(self.portfolio.equity_history),
        )


def run_simulation(initial_capital=20_000.0, days=365, seed=7, config_path=None,
                   verbose=False, arrival_multiplier=None, edge_shrinkage=None):
    engine = PaperEngine(initial_capital, seed, config_path,
                         arrival_multiplier, edge_shrinkage)
    for day in range(days):
        snap = engine.step(day)
        if verbose and (day % 30 == 0 or day == days - 1):
            print(
                f"day={day:3d} cash={snap['cash']:9.2f} invested={snap['invested']:9.2f} "
                f"positions={snap['open_positions']:3d} trades={snap['trades_total']:4d} "
                f"candidates={snap['candidates_today']:3d}"
            )
    return engine.result(days, liquidate=True)


def save_result(result: SimulationResult, outdir: str | Path, prefix="live"):
    p = Path(outdir)
    p.mkdir(parents=True, exist_ok=True)
    (p / f"{prefix}_summary.json").write_text(json.dumps(result.summary, indent=2))
    result.trades.to_csv(p / f"{prefix}_trades.csv", index=False)
    result.sectors.to_csv(p / f"{prefix}_sectors.csv", index=False)
    result.equity.to_csv(p / f"{prefix}_equity.csv", index=False)
