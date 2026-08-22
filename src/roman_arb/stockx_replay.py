from __future__ import annotations
import re
import numpy as np
import pandas as pd


def _money(x):
    if pd.isna(x): return np.nan
    return float(re.sub(r"[^0-9.\-]", "", str(x)))


def _resolve_columns(df: pd.DataFrame):
    norm = {c.lower().replace("_", " ").strip(): c for c in df.columns}
    def pick(*names):
        for n in names:
            if n in norm: return norm[n]
        raise KeyError(f"Missing one of columns: {names}")
    return {
        "date": pick("order date", "orderdate"),
        "name": pick("sneaker name", "sneakername"),
        "price": pick("sale price", "saleprice"),
        "size": pick("shoe size", "shoesize"),
    }


def run_stockx_replay(csv_path, lookback=40, horizon=8, entry_discount=0.12,
                      buy_fee=0.03, sell_fee=0.12, min_history=15):
    """Walk-forward research replay on transaction tape.

    NOT a synchronized executable cross-market backtest. Each historical sale is
    treated as a hypothetical acquisition opportunity and the future exit proxy
    is the median of the next `horizon` same-product/size transactions.
    """
    df = pd.read_csv(csv_path)
    cols = _resolve_columns(df)
    x = pd.DataFrame({
        "date": pd.to_datetime(df[cols["date"]]),
        "name": df[cols["name"]].astype(str),
        "size": df[cols["size"]].astype(str),
        "price": df[cols["price"]].map(_money),
    }).dropna().sort_values("date").reset_index(drop=True)

    trades = []
    for (name, size), g in x.groupby(["name", "size"], sort=False):
        g = g.sort_values("date").reset_index(drop=True)
        prices = g["price"].to_numpy(float)
        for i in range(min_history, len(g)-horizon):
            hist = prices[max(0, i-lookback):i]
            if len(hist) < min_history: continue
            fair = float(np.median(hist))
            entry = prices[i]
            if entry >= fair * (1-entry_discount): continue
            future = prices[i+1:i+1+horizon]
            exit_price = float(np.median(future))
            cost = entry * (1+buy_fee)
            proceeds = exit_price * (1-sell_fee)
            pnl = proceeds - cost
            trades.append({
                "date": g.loc[i, "date"], "name": name, "size": size,
                "entry": entry, "past_median": fair, "exit_proxy": exit_price,
                "pnl": pnl, "roi": pnl/cost,
            })
    t = pd.DataFrame(trades)
    if t.empty:
        summary = {"trades": 0, "mean_roi": 0.0, "median_roi": 0.0, "win_rate": 0.0}
    else:
        summary = {
            "trades": len(t), "mean_roi": float(t.roi.mean()),
            "median_roi": float(t.roi.median()), "win_rate": float((t.pnl>0).mean()),
            "total_pnl_per_one_unit_each_trade": float(t.pnl.sum()),
        }
    return summary, t
