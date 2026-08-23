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
score_i = LCB(net_profit_i) / (capital_i * E[holding_days_i])
```

Net profit is after configured:

- buyer and seller fees
- payment processing
- shipping / insurance
- authentication / grading
- FX friction
- repair / condition costs
- expected returns / fraud losses
- configured taxes
- forced-liquidation / exit markdowns

The system does **not** try to maximize capital utilization. With EUR 10k it may prefer a smaller number of high-ROIC opportunities and keep cash idle.

## Simple model stack

The current pre-live stack is intentionally interpretable:

1. hierarchical fair value: product -> family -> sector -> global
2. robust PCA residual factors on returns, never raw price levels
3. dynamic Kalman factor filter
4. sale-hazard / expected time-to-sale model
5. seller / route Beta posterior
6. lightweight text + image-condition risk inputs
7. EWMA + Page-Hinkley regime detection
8. robust cross-market median/MAD anomaly model
9. conservative ensemble + LCB veto

PCA/factors are overlays only: they are bounded and cannot manufacture a large bargain by themselves.

## Universe

The maximal catalog currently contains hundreds of resale sub-sectors spanning cards, watches, LEGO, sneakers, cameras, luxury, music gear, electronics, games, collectibles and more. A large source registry separates:

- official / credentialed APIs
- partner feeds
- manual / CSV snapshot sources
- restricted / unavailable sources

No source is treated as live unless an authorized feed is actually available.

## Data and live collection

Implemented feed adapters include official/credentialed paths for eBay, StockX, Reverb, Etsy, Mercado Libre and Rakuten, plus a universal CSV snapshot adapter.

Point-in-time observations are stored append-only in SQLite. Entity matching is deliberately conservative around size, grade, storage, model/reference and condition. Quote freshness is part of execution logic so stale bids cannot become fake locked arbitrage.

## EUR 10k allocation

The simple allocator ranks by LCB net profit per capital-day and applies:

- cash buffer
- per-item caps
- larger caps only for locked/executable opportunities
- sector and source concentration limits
- duplicate-entity vetoes

## 48-hour shadow experiment

The first real validation will run for 48 hours with EUR 10,000 virtual capital. We will track:

- NAV / cash / inventory
- raw vs qualified signals
- executable exit rate
- net ROIC
- capital utilization and capital-days
- forecast error and calibration
- 1h / 6h / 24h / 48h marks
- sale/execution outcomes separately from theoretical marks
- performance by sector, source, route and model

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

- `src/roman_arb/model_stack.py` — unified simple model stack
- `src/roman_arb/hierarchy.py` — hierarchical fair value
- `src/roman_arb/factors.py` — robust PCA overlay
- `src/roman_arb/kalman.py` — dynamic factor filter
- `src/roman_arb/liquidity.py` — sale hazard
- `src/roman_arb/seller.py` — seller posterior
- `src/roman_arb/condition_model.py` — condition risk
- `src/roman_arb/regime.py` — regime detector
- `src/roman_arb/anomaly.py` — cross-market anomaly model
- `src/roman_arb/allocator.py` — EUR 10k capital-day allocator
- `src/roman_arb/feeds/` — feed adapters
- `src/roman_arb/snapshot.py` — point-in-time snapshot store
- `docs/` — Reselling BOT public dashboard

## Safety / research status

Research software only. No warranty. Marketplace fee schedules and access rules change; real deployment must use current account-specific costs and authorized APIs/feeds. Shadow results are not guarantees of achievable return.
