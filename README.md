# CODICE PER ROMAN

Event-driven **paper-trading / research engine** for cross-market arbitrage in physical goods.

The project models 20 resale sectors (graded cards, watches, LEGO, sneakers, cameras, music gear, electronics, etc.) under one capital constraint. It ranks opportunities by a conservative lower-confidence-bound (LCB) estimate of net profit per capital-day, routes each item to the best simulated exit venue after fees, and tracks cash, inventory, turnover, realized P&L and capacity.

> **Important:** the default `live` mode is a synthetic live market used for research and paper trading. It does **not** scrape marketplaces, submit orders, or claim that simulated returns are achievable. Real marketplace adapters must use authorized APIs/feeds and current terms/fees.

## Core idea

For candidate listing `j`, buy venue `a`, exit venue `b`:

```text
net_proceeds = estimated_exit_price * (1 - sell_fee[b]) - exit_fixed_cost
estimated_profit = net_proceeds - acquisition_cost
LCB_profit = estimated_profit - z * model_uncertainty
score = LCB_profit / (capital_required * expected_holding_days)
```

Capital scarcity is endogenous. When utilization rises, the required score rises via a shadow price of capital; the engine therefore keeps only the best inventory rather than using a fixed ROI threshold.

## 20 sectors

1. TCG graded cards
2. Modern watches
3. LEGO sealed
4. Graded sports cards
5. Deadstock sneakers
6. Camera lenses
7. Sealed TCG
8. Numismatic coins
9. Graded comics
10. Synths / drum machines
11. Retro games
12. Camera bodies
13. Luxury handbags
14. Rare vinyl
15. Guitar pedals
16. High-end headphones
17. GPUs / PC parts
18. Consoles / handhelds
19. Premium smartphones
20. Laptops / tablets

Parameters live in `config/markets.json`; they are intentionally editable and should be re-estimated from point-in-time data. Two parameters are deliberately exposed because they dominate capacity: `arrival_multiplier` controls how many prefiltered candidate listings the scanner sees, and `edge_shrinkage` controls how much of an apparent discount survives winner's-curse/hidden-quality correction.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e .

# One accelerated synthetic-live year with EUR 20k
python scripts/run_live.py --capital 20000 --days 365 --seed 7

# Console demo: repeated simulated sessions
python scripts/run_live_console.py --capital 20000 --ticks 30 --sleep 0.25

# Capacity curve
python scripts/run_capacity.py --capitals 2500 5000 10000 20000 25000 50000 100000 --years 100

# Monte Carlo for EUR 20k
python scripts/run_monte_carlo.py --capital 20000 --years 250

# Arrival-rate x true-edge sensitivity
python scripts/run_sensitivity.py --capital 20000 --years 20
```

Outputs are written under `outputs/` as CSV/JSON.

## Simulated-live architecture

```text
Synthetic/real adapters
        |
        v
normalized Listing events
        |
        +--> entity/sector normalization
        +--> fee + route engine
        +--> fair-value estimate + uncertainty
        +--> LCB net profit
        +--> expected time-to-sale
        |
        v
score = LCB profit / (capital * days)
        |
        v
capital-aware portfolio allocator
        |
        v
paper execution -> inventory -> stochastic exit -> realized cash P&L
```

The interfaces intentionally separate **market ingestion** from **trading logic**, so a future authorized StockX/eBay/Chrono24/etc. adapter does not require rewriting the portfolio engine.

## Historical StockX research replay

`scripts/run_stockx_replay.py` accepts the public StockX 2019 data-contest CSV. This is explicitly labelled a **research replay / pseudo-backtest**, not a synchronized cross-market executable backtest, because the public file contains realized transactions rather than contemporaneous order books across venues.

```bash
python scripts/run_stockx_replay.py path/to/StockX-Data-Contest-2019-3.csv
```

The replay is walk-forward: the reference price at a transaction can only use earlier transactions of the same sneaker/size. Buyer/seller fees are explicit parameters.

## Current-fee warning

Fee schedules change by country, category, seller tier and date. Values in `config/markets.json` are research defaults, **not authoritative current quotes**. Before any real trade, replace them with verified current fee schedules and shipping/payment costs for the actual account and jurisdiction.

The simulator sets Swiss import tax to **0%** because that is the requested research assumption. Do not interpret that as tax advice.

## Risk controls

- cash-only: no leverage
- per-item/sector concentration caps
- stochastic fill probability
- quality/condition uncertainty
- model error / winner's curse via LCB
- stochastic holding periods
- rare operational-loss events
- forced liquidation after maximum holding time
- no mark-to-model P&L: returns are based on realized exits plus liquidation of residual inventory at the end of the horizon

## Files

- `src/roman_arb/models.py` — event/position/trade dataclasses
- `src/roman_arb/config.py` — config loader
- `src/roman_arb/fees.py` — venue fee routing
- `src/roman_arb/stream.py` — synthetic live event generator
- `src/roman_arb/strategy.py` — valuation, LCB and score
- `src/roman_arb/portfolio.py` — capital-aware paper portfolio
- `src/roman_arb/simulator.py` — event-driven engine
- `src/roman_arb/stockx_replay.py` — walk-forward historical research replay
- `src/roman_arb/metrics.py` — summary/capacity metrics
- `scripts/` — runnable entry points
- `tests/` — unit tests

## What would make this a real live system

1. Authorized listing/order-book APIs or licensed feeds.
2. A persistent product/entity graph (SKU/reference/card grade/etc.).
3. Historical point-in-time snapshots for model training and honest backtesting.
4. Actual account-specific fee/shipping/FX tables.
5. Real fill/return/fraud/condition outcomes.
6. Monitoring + alerts; still paper-only until forward validation is satisfactory.

## License

MIT. Research software; no warranty and no investment, tax or legal advice.
