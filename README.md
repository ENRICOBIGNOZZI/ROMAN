# Reselling BOT

**Cross-market resale arbitrage research and shadow-trading engine.**

Reselling BOT searches physical-goods resale markets under a single capital constraint, estimates fully net opportunity economics, and ranks candidates by conservative expected profit per capital-day.

> Current mode: **shadow / paper only**. No real orders are submitted. The initial validation capital is **EUR 10,000**.

## Public monitor

The dashboard lives in `docs/` and is designed for GitHub Pages. Once Pages is enabled for this repository with **GitHub Actions** as the source, the public URL is expected to be:

`https://enricobignozzi.github.io/ROMAN/`

The page starts in `PRE-SHADOW` with zero P&L and no invented market data. When an authorized market feed actually returns rows, the same frontend reads the live `dashboard.json` endpoint.

A green network smoke with **zero market rows is only a software-health check**. It is not market-data validation and it is not evidence of profitability.

## Objective

For candidate `i`, Reselling BOT optimizes a lower-confidence-bound estimate of **net** profit per capital-day:

```text
score_i = LCB(net_profit_i) / (capital_i * E[holding_days_i])
```

Net profit is after configured buyer/seller fees, payment processing, shipping/insurance, authentication/grading, FX friction, repair/condition costs, expected returns/fraud losses, configured taxes, and exit markdowns.

The system does **not** try to maximize capital utilization. With EUR 10k it may rationally keep cash idle.

## Online model stack

The shadow/live stack is intentionally interpretable:

1. hierarchical fair value: product -> family -> sector -> global;
2. robust PCA residual factors on temporal returns, never raw price levels;
3. dynamic Kalman factor filter;
4. sale-hazard / expected time-to-sale model;
5. seller / route Beta posterior from explicit seller-quality outcomes;
6. transparent text/metadata condition risk; an image-defect input exists as a future hook, but no vision model is connected today;
7. two-sided EWMA + Page-Hinkley-style regime detection with short stress persistence;
8. robust cross-market median/MAD anomaly diagnostics;
9. dependence-aware conservative ensemble + LCB veto;
10. provisional posterior-confidence budget across the wide universe.

The factor layer is an overlay only: it is bounded and cannot manufacture a large bargain by itself. For a non-executable inventory trade, ROMAN also prevents several transformations of the same current comparables from counting as independent model votes.

## Fair value is not executable cash

ROMAN keeps valuation and execution separate. A fair value is a model state. Expected cash proceeds use the selected concrete exit route when route evidence is available, with route-specific fees, fixed costs, shipping and FX friction applied once.

Fresh executable bids are treated separately from public asks. A favorable mark is **not** a sale and is never reported as realized P&L.

## Universe and feeds

The catalog spans cards, watches, LEGO, sneakers, cameras, luxury goods, music gear, electronics, games and collectibles. The source registry separates:

- official / credentialed APIs;
- partner feeds;
- manual / CSV snapshot sources;
- restricted / unavailable sources.

Implemented adapters include eBay, StockX, Reverb, Etsy, Mercado Libre and Rakuten, plus a universal CSV snapshot adapter. A source is not treated as live unless the corresponding authorized feed is available.

Point-in-time observations are append-only in SQLite. Entity matching is conservative around size, grade, storage, model/reference and condition. Quote freshness is part of execution logic so stale bids cannot become fake locked arbitrage.

## EUR 10k allocation

The allocator ranks by LCB net profit per capital-day and applies a cash buffer, per-item limits, higher caps only for locked/executable opportunities, sector/source concentration limits, maximum forecast holding horizon, and duplicate-entity vetoes.

## 48-hour shadow experiment

The first genuine market validation begins only after at least one authorized feed produces real point-in-time rows. The 48-hour run tracks:

- NAV / cash / inventory;
- raw vs qualified signals;
- executable exit rate;
- net ROIC;
- utilization and capital-days;
- forecast error and calibration;
- 1h / 6h / 24h / 48h marks;
- executable outcomes separately from theoretical marks;
- performance by sector, source, route and model.

The current posterior/FDR layer is explicitly **provisional**: `ensemble_confidence` is not yet a calibrated posterior probability. Exact calibration claims require forward outcomes.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

Shadow/live daemon (authorized read feeds only, no order submission):

```bash
roman-live --capital 10000 --interval 300
# alias:
roman-shadow --capital 10000 --interval 300
```

The script wrapper is equivalent:

```bash
python scripts/run_live_daemon.py --capital 10000 --interval 300
```

Synthetic Monte Carlo is a **separate research/stress harness** and does not validate the live model or current market opportunities:

```bash
roman-sim --capital 20000 --days 365 --seed 7
```

## Credentials

Use only authorized API credentials and keep them in environment variables / secret storage. `.env.example` lists the supported names. Never commit real credentials. The experiment manifest records credential **presence only**, never secret values.

## Repository structure

- `src/roman_arb/live.py` — canonical shadow economic pipeline
- `src/roman_arb/daemon.py` — long-lived scheduler / dashboard server
- `src/roman_arb/model_stack.py` — unified online model stack
- `src/roman_arb/hierarchy.py` — hierarchical fair value
- `src/roman_arb/factors.py` — robust PCA overlay
- `src/roman_arb/kalman.py` — dynamic factor filter
- `src/roman_arb/liquidity.py` — sale hazard
- `src/roman_arb/seller.py` — seller posterior
- `src/roman_arb/condition_model.py` — text/metadata condition risk + optional image hook
- `src/roman_arb/regime.py` — regime detector
- `src/roman_arb/anomaly.py` — cross-market anomaly diagnostic
- `src/roman_arb/allocator.py` — EUR 10k capital-day allocator
- `src/roman_arb/shadow_ledger.py` — path-dependent shadow inventory/P&L ledger
- `src/roman_arb/feeds/` — authorized feed adapters
- `src/roman_arb/snapshot.py` — point-in-time snapshot store
- `src/roman_arb/simulator.py` — separate synthetic simulation harness
- `docs/` — public dashboard

## Safety / research status

Research software only. No warranty. Marketplace fee schedules, access rules and account-specific costs change. Real deployment must use current authorized APIs/feeds and current executable costs. Shadow results are not guarantees of achievable return.
