# Reselling BOT

**Cross-market resale arbitrage research and shadow-trading engine.**

Reselling BOT searches a maximal universe of physical-goods resale markets under a single capital constraint, estimates **fully net** opportunity economics, and ranks candidates by conservative expected profit per capital-day.

> Current mode: **shadow / paper only**. No real orders are submitted. The initial validation capital is **EUR 10,000**.

## Public monitor

The dashboard lives in `docs/` and is designed for GitHub Pages. Once Pages is enabled for this repository with **GitHub Actions** as the source, the public URL is expected to be:

`https://enricobignozzi.github.io/ROMAN/`

The page starts in `PRE-SHADOW` with zero P&L and no invented market data. When the server is connected, the same frontend reads the live `dashboard.json` endpoint.

## Objective

For candidate `i`, Reselling BOT optimizes a lower-confidence-bound estimate of **net** profit per capital-day:

```text
score_i = LCB(net_ROI_i) / E[holding_days_i]
LCB(net_ROI_i) = E[net_ROI_i] - z * sigma(net_ROI_i)
```

Net profit is after configured buyer/seller fees, payment processing, shipping, insurance, authentication/grading, FX friction, repair/condition costs, expected returns/fraud losses, configured taxes and exit markdowns.

The system does **not** try to maximize capital utilization. With EUR 10k it may prefer a smaller number of high-ROIC opportunities and keep cash idle.

## One unified model

ROMAN no longer treats fair value, factors, liquidity, seller quality and cross-market anomalies as independent models that vote on a purchase.

The core predictive object is:

```text
p(net_payoff, time_to_sale | item_information, market_state)
```

The implementation has four blocks:

1. **Market state** — PCA/Kalman/regime information summarizes common conditions and makes only bounded adjustments.
2. **Price + time-to-sale** — hierarchical partial pooling (`product -> family -> sector -> global`) estimates sparse fair values; condition, seller/route information and comparables enter as covariates/evidence; the sale hazard supplies expected holding time.
3. **Net payoff distribution** — every configured cost is deducted before estimating expected net ROI and uncertainty.
4. **Decision** — one LCB is converted into expected payoff per capital-day and passed to the capital allocator.

The old agreement-gated ensemble remains available as a standalone legacy component for experiments, but it is no longer used by `SimpleModelStack`.

## Universe

The maximal catalog currently contains hundreds of resale sub-sectors spanning cards, watches, LEGO, sneakers, cameras, luxury, music gear, electronics, games, collectibles and more. A large source registry separates official/credentialed APIs, partner feeds, manual/CSV snapshot sources and restricted/unavailable sources.

No source is treated as live unless an authorized feed is actually available.

## Data and live collection

Implemented feed adapters include official/credentialed paths for eBay, StockX, Reverb, Etsy, Mercado Libre and Rakuten, plus a universal CSV snapshot adapter.

Point-in-time observations are stored append-only in SQLite. Entity matching is deliberately conservative around size, grade, storage, model/reference and condition. Quote freshness is part of execution logic so stale bids cannot become fake locked arbitrage.

## EUR 10k allocation

The allocator ranks by LCB net profit per capital-day and applies cash buffer, per-item caps, sector/source concentration limits, duplicate-entity vetoes and explicit slow-inventory limits.

## 48-hour shadow experiment

The first real validation will run for 48 hours with EUR 10,000 virtual capital. We will track NAV/cash/inventory, raw vs qualified candidates, executable exit rate, net ROIC, capital utilization and capital-days, forecast error/calibration, 1h/6h/24h/48h marks, sale/execution outcomes and performance by sector/source/route.

A favorable mark is **not** counted as a realized sale.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

Collector/shadow daemon:

```bash
python scripts/run_live_daemon.py --capital 10000 --interval 300
```

Docker deployment files are included in the repository.

## Repository structure

- `src/roman_arb/model_stack.py` — compatibility entrypoint
- `src/roman_arb/unified_model.py` — unified payoff/time-to-sale predictive model
- `src/roman_arb/hierarchy.py` — hierarchical partial pooling for fair value
- `src/roman_arb/factors.py` — robust PCA market-state features
- `src/roman_arb/kalman.py` — dynamic factor state
- `src/roman_arb/liquidity.py` — sale hazard
- `src/roman_arb/seller.py` — seller/route posterior
- `src/roman_arb/condition_model.py` — condition covariates
- `src/roman_arb/regime.py` — regime state
- `src/roman_arb/anomaly.py` — robust comparable-price evidence
- `src/roman_arb/allocator.py` — EUR 10k capital-day allocator
- `src/roman_arb/feeds/` — feed adapters
- `src/roman_arb/snapshot.py` — point-in-time snapshot store
- `docs/` — Reselling BOT public dashboard

See `MODELS.md` for the compact model specification.

## Safety / research status

Research software only. No warranty. Marketplace fee schedules and access rules change; real deployment must use current account-specific costs and authorized APIs/feeds. Shadow results are not guarantees of achievable return.
