from __future__ import annotations
import numpy as np
import pandas as pd


def summarize(initial_capital: float, cash: float, positions, trades, capital_days: float, utilization_sum: float, days: int):
    # residual inventory should be liquidated before calling for terminal metrics
    pnl = cash - initial_capital
    rois = np.array([t.roi for t in trades], dtype=float) if trades else np.array([])
    pnls = np.array([t.pnl for t in trades], dtype=float) if trades else np.array([])
    holds = np.array([t.holding_days for t in trades], dtype=float) if trades else np.array([])
    turnover = sum(t.acquisition_cost for t in trades) / initial_capital
    utilization = utilization_sum / max(days, 1)
    wins = float((pnls > 0).mean()) if len(pnls) else 0.0
    return {
        "initial_capital": initial_capital,
        "final_cash": cash,
        "pnl": pnl,
        "return": pnl / initial_capital,
        "trades": len(trades),
        "win_rate": wins,
        "mean_trade_roi": float(rois.mean()) if len(rois) else 0.0,
        "median_trade_roi": float(np.median(rois)) if len(rois) else 0.0,
        "mean_holding_days": float(holds.mean()) if len(holds) else 0.0,
        "turnover": turnover,
        "utilization": utilization,
        "problem_trades": int(sum(t.problem for t in trades)),
        "forced_trades": int(sum(t.forced for t in trades)),
    }


def trades_frame(trades):
    return pd.DataFrame([t.__dict__ for t in trades])


def sector_frame(trades):
    df = trades_frame(trades)
    if df.empty:
        return df
    g = df.groupby("sector").agg(
        trades=("pnl", "size"), pnl=("pnl", "sum"),
        mean_roi=("roi", "mean"), median_roi=("roi", "median"),
        mean_holding=("holding_days", "mean"), capital=("acquisition_cost", "sum")
    )
    return g.sort_values("pnl", ascending=False).reset_index()
