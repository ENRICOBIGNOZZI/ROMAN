#!/usr/bin/env python3
"""Stateful synthetic-live paper console.

No marketplace connections and no real orders. Inventory stays open across ticks.
"""
import argparse, time
from roman_arb.simulator import PaperEngine

p=argparse.ArgumentParser()
p.add_argument("--capital",type=float,default=20000)
p.add_argument("--ticks",type=int,default=30)
p.add_argument("--sleep",type=float,default=.25)
p.add_argument("--seed",type=int,default=500)
p.add_argument("--arrival-multiplier",type=float,default=None)
p.add_argument("--edge-shrinkage",type=float,default=None)
p.add_argument("--liquidate-at-end",action="store_true")
a=p.parse_args()
engine=PaperEngine(a.capital,a.seed,arrival_multiplier=a.arrival_multiplier,edge_shrinkage=a.edge_shrinkage)
print("SIMULATED LIVE PAPER MODE — no real orders / no scraping")
for day in range(a.ticks):
    s=engine.step(day)
    print(
      f"day={day:03d} cash={s['cash']:9.2f} invested={s['invested']:9.2f} "
      f"open={s['open_positions']:3d} cand={s['candidates_today']:3d} "
      f"qualified={s['qualified_today']:2d} opened={s['opened_today']:2d} closed={s['closed_today']:2d}"
    )
    time.sleep(a.sleep)
if a.liquidate_at_end:
    result=engine.result(a.ticks,liquidate=True)
    print(f"terminal cash={result.summary['final_cash']:.2f} return={100*result.summary['return']:.2f}%")
else:
    result=engine.result(a.ticks,liquidate=False)
    print(f"paper cash={engine.portfolio.cash:.2f}; open inventory cost={engine.portfolio.invested:.2f}; realized trades={len(engine.portfolio.trades)}")
