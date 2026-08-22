#!/usr/bin/env python3
import argparse, json
from pathlib import Path
from roman_arb.stockx_replay import run_stockx_replay

p=argparse.ArgumentParser(description="Walk-forward research replay on the StockX 2019 data-contest transaction CSV")
p.add_argument("csv")
p.add_argument("--lookback",type=int,default=40)
p.add_argument("--horizon",type=int,default=8)
p.add_argument("--entry-discount",type=float,default=.12)
p.add_argument("--buy-fee",type=float,default=.03)
p.add_argument("--sell-fee",type=float,default=.12)
p.add_argument("--out",default="outputs")
a=p.parse_args()
summary,trades=run_stockx_replay(a.csv,a.lookback,a.horizon,a.entry_discount,a.buy_fee,a.sell_fee)
out=Path(a.out);out.mkdir(exist_ok=True)
trades.to_csv(out/"stockx_replay_trades.csv",index=False)
(out/"stockx_replay_summary.json").write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
print("WARNING: research replay only; not synchronized executable cross-market backtest.")
