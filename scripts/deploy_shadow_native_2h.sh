#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/ENRICOBIGNOZZI/ROMAN.git"
ROOT="${RESELLING_BOT_HOME:-$HOME/reselling-bot}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
HOURS="${RESELLING_BOT_HOURS:-2}"
INTERVAL="${RESELLING_BOT_INTERVAL:-120}"
PORT="${RESELLING_BOT_PORT:-8787}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python3 is required" >&2
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

STAMP="$(date +%Y%m%d_%H%M%S)"
for f in data/roman_snapshots.sqlite data/roman_tracking.sqlite data/roman_shadow.sqlite outputs/live/dashboard.json outputs/live/diagnostic_report.json outputs/live/diagnostic_report.md; do
  if [ -f "$f" ]; then
    mv "$f" "outputs/archive/${STAMP}_$(basename "$f")"
  fi
done

if [ ! -d .venv ]; then
  "$PYTHON_BIN" -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
python -m pip install -e .

# Load authorized credentials if present. With no configured feed the process is
# still useful as a software smoke, but it must remain PRE-SHADOW and cannot be
# interpreted as market validation.
set -a
# shellcheck disable=SC1091
source .env
set +a

if [ -f outputs/live/2h.pid ]; then
  OLD_PID="$(cat outputs/live/2h.pid || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" >/dev/null 2>&1; then
    kill "$OLD_PID" || true
    sleep 1
  fi
fi

LOG="outputs/live/2h.log"
: > "$LOG"

(
  roman-live \
    --capital 10000 \
    --interval "$INTERVAL" \
    --queries-per-source 1 \
    --limit 20 \
    --health-port "$PORT" \
    --max-hours "$HOURS" \
    --snapshot-db data/roman_snapshots.sqlite \
    --tracking-db data/roman_tracking.sqlite \
    --shadow-db data/roman_shadow.sqlite \
    --dashboard outputs/live/dashboard.json
  python scripts/report_shadow.py \
    --shadow-db data/roman_shadow.sqlite \
    --snapshot-db data/roman_snapshots.sqlite \
    --dashboard outputs/live/dashboard.json \
    --out outputs/live/diagnostic_report
) >> "$LOG" 2>&1 &
PID=$!
echo "$PID" > outputs/live/2h.pid

READY=0
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 2
done

if [ "$READY" -eq 0 ]; then
  echo "Reselling BOT did not become healthy. Last log lines:" >&2
  tail -n 80 "$LOG" >&2 || true
  exit 1
fi

echo
curl -fsS "http://127.0.0.1:${PORT}/health" || true
echo

echo "Reselling BOT native ${HOURS}h shadow diagnostic started."
echo "PID:       $PID"
echo "Dashboard: http://127.0.0.1:${PORT}/"
echo "JSON:      http://127.0.0.1:${PORT}/dashboard.json"
echo "Log:       $ROOT/$LOG"
echo "Report:    $ROOT/outputs/live/diagnostic_report.md (written after completion)"
echo
echo "Watch now: tail -f '$ROOT/$LOG'"

if command -v tailscale >/dev/null 2>&1; then
  echo
  echo "Tailscale detected. Attempting optional dashboard exposure..."
  if tailscale funnel --bg --https=443 "http://127.0.0.1:${PORT}" 2>/dev/null; then
    tailscale funnel status || true
  else
    echo "Funnel was not enabled automatically; local dashboard is still running."
  fi
fi
