# ROMAN — server shadow validation

ROMAN is paper-only. It reads authorized market data, maintains a virtual inventory ledger and never submits an order.

## Before calling anything a live validation

A process with zero market rows is only a software/network smoke. For a genuine 48-hour market test, configure at least one supported authorized feed in `.env`.

Supported credential groups are listed in `.env.example` (eBay, StockX, Reverb, Etsy, Mercado Libre and Rakuten). Do not commit real secrets.

## Native diagnostic smoke

This path may run even without credentials. With no active feed it should remain `PRE-SHADOW`; that is expected and is not performance evidence.

```bash
git clone https://github.com/ENRICOBIGNOZZI/ROMAN.git
cd ROMAN
cp .env.example .env
bash scripts/deploy_shadow_native_2h.sh
```

The script archives any previous snapshots, scheduler state, shadow ledger and dashboard before starting a new diagnostic path.

Useful endpoints while it is running:

```bash
curl http://127.0.0.1:8787/health
curl http://127.0.0.1:8787/dashboard.json
```

Browser dashboard:

```text
http://127.0.0.1:8787/
```

After completion, `outputs/live/diagnostic_report.md` and `.json` summarize the collected evidence.

## EUR 10,000 / 48-hour market shadow

After adding at least one authorized feed credential to `.env`:

```bash
bash scripts/deploy_shadow_48h.sh
```

The 48-hour deployment refuses to start if no supported feed credentials are configured. Before the new process starts, it archives the previous `roman_snapshots.sqlite`, `roman_tracking.sqlite`, `roman_shadow.sqlite` and live report/dashboard artifacts so old inventory cannot contaminate the new path.

Docker/Compose run the canonical `roman-live` entrypoint:

```bash
docker compose logs -f reselling-bot
curl http://127.0.0.1:8787/health
curl http://127.0.0.1:8787/dashboard.json
```

The service binds the dashboard/API to localhost by default. Optional Tailscale exposure is attempted by the deployment scripts when Tailscale is installed; do not expose an unauthenticated dashboard to the public internet unless you explicitly intend to.

## Persisted evidence

- `data/roman_snapshots.sqlite` — append-only point-in-time listing observations;
- `data/roman_tracking.sqlite` — adaptive query scan/signal/failure statistics;
- `data/roman_shadow.sqlite` — path-dependent positions, cycle records and NAV marks;
- `data/fx_rates.json` — point-in-time ECB reference FX book when refresh succeeds;
- `outputs/live/dashboard.json` — current normalized dashboard state;
- `outputs/live/diagnostic_report.{json,md}` — post-run diagnostic summary when generated.

No secret value is written to these artifacts by the runtime.

## What a valid run must establish

A useful 24–48h run should show real snapshot rows, stable exact-entity matching, costs and FX applied consistently, candidates moving through the evidence/FDR gates, path-dependent capital allocation, and forward executable/mark behavior. A green process with zero rows establishes none of those market claims.

Seller-quality learning additionally requires explicit fulfilment/authenticity/return-quality outcomes; price-shadow observations alone correctly leave the seller posterior near its prior.

## Synthetic research is separate

For Monte Carlo/stress work use:

```bash
roman-sim --capital 20000 --days 365 --seed 7
```

Synthetic results are calibration exercises, not live-market validation.
