#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/ENRICOBIGNOZZI/ROMAN.git"
ROOT="${RESELLING_BOT_HOME:-$HOME/reselling-bot}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

if [ -d "$ROOT/.git" ]; then
  git -C "$ROOT" fetch origin main
  git -C "$ROOT" reset --hard origin/main
else
  rm -rf "$ROOT"
  git clone "$REPO_URL" "$ROOT"
fi

cd "$ROOT"
[ -f .env ] || cp .env.example .env
mkdir -p data outputs/live outputs/archive

# Load credentials only for a preflight presence check. Values are never printed.
set -a
# shellcheck disable=SC1091
source .env
set +a

HAS_AUTHORIZED_FEED=0
if [ -n "${EBAY_CLIENT_ID:-}" ] && [ -n "${EBAY_CLIENT_SECRET:-}" ]; then HAS_AUTHORIZED_FEED=1; fi
if [ -n "${STOCKX_API_KEY:-}" ] && [ -n "${STOCKX_ACCESS_TOKEN:-}" ]; then HAS_AUTHORIZED_FEED=1; fi
if [ -n "${REVERB_TOKEN:-}" ]; then HAS_AUTHORIZED_FEED=1; fi
if [ -n "${ETSY_API_KEY:-}" ]; then HAS_AUTHORIZED_FEED=1; fi
if [ -n "${MELI_ACCESS_TOKEN:-}" ]; then HAS_AUTHORIZED_FEED=1; fi
if [ -n "${RAKUTEN_APPLICATION_ID:-}" ] && [ -n "${RAKUTEN_ACCESS_KEY:-}" ]; then HAS_AUTHORIZED_FEED=1; fi

if [ "$HAS_AUTHORIZED_FEED" -ne 1 ]; then
  echo "No authorized market feed is configured in .env." >&2
  echo "Refusing to label a zero-data process as a 48h market validation." >&2
  echo "Configure at least one supported read-only feed, or use the CI/native diagnostic smoke instead." >&2
  exit 2
fi

# Archive prior evidence before starting a genuinely fresh path-dependent ledger.
STAMP="$(date +%Y%m%d_%H%M%S)"
for f in data/roman_snapshots.sqlite data/roman_tracking.sqlite data/roman_shadow.sqlite outputs/live/dashboard.json outputs/live/diagnostic_report.json outputs/live/diagnostic_report.md; do
  if [ -f "$f" ]; then
    mv "$f" "outputs/archive/${STAMP}_$(basename "$f")"
  fi
done

docker compose down --remove-orphans || true
docker compose build --pull
docker compose up -d

READY=0
for _ in $(seq 1 40); do
  if curl -fsS http://127.0.0.1:8787/health >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 2
done

if [ "$READY" -ne 1 ]; then
  echo "Reselling BOT did not become healthy. Last container logs:" >&2
  docker logs --tail 120 reselling-bot >&2 || true
  exit 3
fi

curl -fsS http://127.0.0.1:8787/health || true

if command -v tailscale >/dev/null 2>&1; then
  echo "Attempting optional HTTPS exposure through Tailscale Funnel..."
  sudo tailscale funnel --bg --https=443 http://127.0.0.1:8787 || {
    echo "Funnel could not be enabled automatically. Localhost access remains available." >&2
  }
  sudo tailscale funnel status || true
else
  echo "Tailscale not found; dashboard/API remain bound to localhost." >&2
fi

echo
echo "Reselling BOT 48h shadow process started with at least one configured authorized feed."
echo "This is still paper-only: no orders are submitted."
echo "Local dashboard: http://127.0.0.1:8787/"
echo "JSON:            http://127.0.0.1:8787/dashboard.json"
echo "Logs:            docker logs -f reselling-bot"
echo "After completion: python scripts/report_shadow.py"
