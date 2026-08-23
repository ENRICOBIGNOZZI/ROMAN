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
mkdir -p data outputs/live

# First experiment is intentionally fresh and bounded. Reset all state that can
# carry information, positions or P&L across shadow runs.
rm -f \
  data/roman_snapshots.sqlite \
  data/roman_tracking.sqlite \
  data/roman_shadow.sqlite \
  outputs/live/dashboard.json

docker compose down --remove-orphans || true
docker compose build --pull
docker compose up -d

for _ in $(seq 1 40); do
  if curl -fsS http://127.0.0.1:8787/health >/dev/null 2>&1; then break; fi
  sleep 2
done

curl -fsS http://127.0.0.1:8787/health || true

if command -v tailscale >/dev/null 2>&1; then
  echo "Attempting public HTTPS exposure through Tailscale Funnel..."
  sudo tailscale funnel --bg --https=443 http://127.0.0.1:8787 || {
    echo "Funnel could not be enabled automatically. Run: sudo tailscale funnel --bg --https=443 http://127.0.0.1:8787" >&2
  }
  sudo tailscale funnel status || true
else
  echo "Tailscale not found; API is available only at http://127.0.0.1:8787" >&2
fi

echo
echo "Reselling BOT 48h shadow experiment started."
echo "Local API: http://127.0.0.1:8787/dashboard.json"
echo "Logs: docker logs -f reselling-bot"
