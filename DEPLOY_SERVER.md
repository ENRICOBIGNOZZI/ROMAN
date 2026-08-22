# ROMAN — server shadow validation

ROMAN is paper-only. It records authorized/API observations and never submits an order.

## First experiment: EUR 10,000, 48 hours

```bash
git clone https://github.com/ENRICOBIGNOZZI/ROMAN.git
cd ROMAN
cp .env.example .env
nano .env                    # add only API credentials you are authorized to use
bash scripts/start_shadow_48h.sh
```

The script archives any previous SQLite state, refreshes an ECB reference FX snapshot, records an experiment manifest, builds the Docker image and runs a bounded 48-hour shadow experiment with EUR 10k. Change duration with `ROMAN_SHADOW_HOURS=24` and capital with `ROMAN_PAPER_CAPITAL=10000`.

During the run (from the server itself):

```bash
curl http://127.0.0.1:8787/health
curl http://127.0.0.1:8787/performance
curl http://127.0.0.1:8787/query-leaderboard
```

Dashboard: `http://127.0.0.1:8787/dashboard`. Keep this endpoint behind localhost/Tailscale/SSH forwarding; do not expose it publicly without authentication.

After the run:

```bash
python scripts/report_shadow.py --capital 10000
python scripts/export_audit.py
```

Persisted evidence:

- `data/roman_snapshots.sqlite` — append-only point-in-time market observations.
- `data/roman_tracking.sqlite` — cycles, every candidate decision, virtual inventory, marks, 1h/6h/24h/48h outcomes, calibration and query-bandit state.
- `data/fx_rates.json` — point-in-time EUR reference FX book.
- `outputs/live/experiment_manifest.json` — Git commit/config hashes and experiment settings; secrets are never recorded.
- `outputs/live/status.json` — scanner health.
- `outputs/live/candidates.*` — posterior opportunities.
- `outputs/live/basket.json` — path-dependent 0/1 allocation.
- `outputs/live/shadow_portfolio.json` — current virtual NAV/cash/inventory.
- `outputs/live/performance.json` — mark hit rate, executable-exit rate, RMSE, mark-Brier score, drawdown, utilization and attribution.
- `outputs/live/query_leaderboard.json` — adaptive query-scheduler ranking, increasingly driven by 24h/48h forward outcomes.

## Continuous mode later

Only after the 24–48h audit looks sensible:

```bash
docker compose up -d --build
docker compose logs -f roman-live
```

The service remains paper-only. Real execution is intentionally not implemented.
