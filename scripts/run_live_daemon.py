from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timezone

from roman_arb.feeds.registry import official_adapters
from roman_arb.live import build_query_plan
from roman_arb.scheduler import AdaptiveQueryScheduler
from roman_arb.snapshot import SnapshotStore


STATUS = {
    "mode": "shadow_collector",
    "started_at": datetime.now(timezone.utc).isoformat(),
    "last_cycle": None,
    "rows_collected": 0,
    "cycles": 0,
    "errors": 0,
    "paper_capital": 10000.0,
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(STATUS, indent=2).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


def health_server(port: int):
    HTTPServer(("0.0.0.0", int(port)), Handler).serve_forever()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--capital", type=float, default=10000.0)
    p.add_argument("--interval", type=int, default=300)
    p.add_argument("--health-port", type=int, default=8787)
    p.add_argument("--queries-per-source", type=int, default=4)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--max-hours", type=float, default=0.0, help="0 means run until stopped")
    p.add_argument("--once", action="store_true")
    p.add_argument("--snapshot-db", default="data/roman_snapshots.sqlite")
    p.add_argument("--tracking-db", default="data/roman_tracking.sqlite")
    args = p.parse_args()

    STATUS["paper_capital"] = float(args.capital)
    threading.Thread(target=health_server, args=(args.health_port,), daemon=True).start()

    store = SnapshotStore(args.snapshot_db)
    scheduler = AdaptiveQueryScheduler(args.tracking_db)
    adapters = official_adapters()
    plan = build_query_plan()
    deadline = time.time() + args.max_hours * 3600.0 if args.max_hours > 0 else None

    try:
        while True:
            cycle_rows = 0
            for source, adapter in adapters.items():
                if not adapter.available():
                    continue
                queries = scheduler.choose(source, plan.get(source, []), args.queries_per_source)
                for query in queries:
                    try:
                        rows = list(adapter.fetch(query, limit=args.limit))
                        store.append(rows)
                        scheduler.record_scan(source, query, len(rows))
                        cycle_rows += len(rows)
                    except Exception as exc:
                        STATUS["errors"] += 1
                        scheduler.record_error(source, query, repr(exc))
            STATUS["rows_collected"] += cycle_rows
            STATUS["cycles"] += 1
            STATUS["last_cycle"] = datetime.now(timezone.utc).isoformat()
            print(json.dumps(STATUS, sort_keys=True), flush=True)

            if args.once or (deadline is not None and time.time() >= deadline):
                break
            time.sleep(max(args.interval, 10))
    finally:
        scheduler.close()
        store.close()


if __name__ == "__main__":
    main()
