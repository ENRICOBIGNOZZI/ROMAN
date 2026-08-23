from __future__ import annotations

import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from roman_arb.fdr import PosteriorFDRSelector
from roman_arb.live import ShadowLiveEngine
from roman_arb.scheduler import AdaptiveQueryScheduler


class State:
    payload = {
        "brand": "Reselling BOT",
        "status": "STARTING",
        "capital": 10000,
        "nav": 10000,
    }
    error = ""
    lock = threading.Lock()


def normalize_payload(p: dict) -> dict:
    q = dict(p)
    ops = []
    for x in q.get("opportunities", []) or []:
        ops.append(
            {
                "entity": x.get("entity"),
                "buy_source": x.get("buy_source"),
                "exit_source": x.get("exit_source"),
                "acquisition_cost": x.get("acquisition_cost", x.get("cost", 0)),
                "net_edge_roi": x.get("net_edge_roi", x.get("net_edge", 0)),
                "lcb_net_roi": x.get("lcb_net_roi", x.get("lcb_roic", 0)),
                "expected_days": x.get("expected_days", 0),
                "score_per_capital_day": x.get(
                    "score_per_capital_day", x.get("score_day", 0)
                ),
                "confidence": x.get("confidence", 0),
                "qualified": x.get("qualified", False),
                "url": x.get("url", ""),
                "cross_border": x.get("cross_border", False),
                "reason": x.get("reason", ""),
            }
        )
    q["opportunities"] = ops

    feeds = []
    for x in q.get("feeds", []) or []:
        raw = str(x.get("status", "waiting")).upper()
        status = (
            "active"
            if raw in ("OK", "ACTIVE")
            else "error"
            if raw in ("ERROR", "FAILED")
            else "waiting"
            if raw in ("NO_CREDENTIALS", "WAITING")
            else "partial"
        )
        feeds.append(
            {
                "name": x.get("name", x.get("source", "unknown")),
                "status": status,
                "rows": x.get("rows", 0),
                "last_update": x.get("last_update", x.get("last", "")),
                # Keep the cause visible in artifacts. The old normalizer dropped
                # this field and made a zero-row network failure look unexplained.
                "error": str(x.get("error") or "")[:500],
            }
        )
    q["feeds"] = feeds
    return q


def _record_scheduler_feedback(tracking_db: str, candidates: list[dict]) -> str:
    """Reward live queries without allowing telemetry failure to stop the engine."""
    sch = None
    try:
        sch = AdaptiveQueryScheduler(tracking_db)
        sch.record_candidates(candidates)
        return ""
    except Exception as exc:
        return str(exc)[:500]
    finally:
        if sch is not None:
            try:
                sch.close()
            except Exception:
                pass


def handler_factory(state):
    html_path = Path("docs/index.html")

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store,max-age=0")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET,OPTIONS")
            self.end_headers()

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/health":
                with state.lock:
                    p = {
                        "ok": not bool(state.error),
                        "status": state.payload.get("status"),
                        "error": state.error,
                    }
                return self._send(200, json.dumps(p).encode())
            if path in ("/dashboard.json", "/api/dashboard"):
                with state.lock:
                    p = normalize_payload(state.payload)
                return self._send(200, json.dumps(p, ensure_ascii=False).encode())
            if path in ("/", "/index.html"):
                if html_path.exists():
                    return self._send(
                        200, html_path.read_bytes(), "text/html; charset=utf-8"
                    )
                return self._send(
                    404, b"dashboard html missing", "text/plain; charset=utf-8"
                )
            self._send(404, b'{"error":"not found"}')

        def log_message(self, *_):
            return

    return Handler


def main():
    p = argparse.ArgumentParser(description="Reselling BOT paper/shadow live daemon")
    p.add_argument("--capital", type=float, default=10000)
    p.add_argument("--interval", type=int, default=300)
    p.add_argument("--queries-per-source", type=int, default=2)
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--health-port", type=int, default=8787)
    p.add_argument("--max-hours", type=float, default=48.0, help="0=until stopped")
    p.add_argument("--once", action="store_true")
    p.add_argument("--snapshot-db", default="data/roman_snapshots.sqlite")
    p.add_argument("--tracking-db", default="data/roman_tracking.sqlite")
    p.add_argument("--shadow-db", default="data/roman_shadow.sqlite")
    p.add_argument("--dashboard", default="outputs/live/dashboard.json")
    args = p.parse_args()

    engine = ShadowLiveEngine(
        capital=args.capital,
        snapshot_db=args.snapshot_db,
        tracking_db=args.tracking_db,
        shadow_db=args.shadow_db,
        dashboard_path=args.dashboard,
        queries_per_source=args.queries_per_source,
        rows_per_query=args.limit,
    )
    fdr = PosteriorFDRSelector(float(os.getenv("ROMAN_FDR_ALPHA", "0.25")))
    state = State()
    state.payload.update(capital=args.capital, nav=args.capital)
    server = ThreadingHTTPServer(
        ("0.0.0.0", args.health_port), handler_factory(state)
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    deadline = time.time() + args.max_hours * 3600 if args.max_hours > 0 else None
    print(
        f"Reselling BOT shadow-live | capital=EUR {args.capital:.2f} | "
        f"dashboard http://0.0.0.0:{args.health_port}/",
        flush=True,
    )

    try:
        while True:
            t0 = time.time()
            try:
                counts = engine.collect_cycle()
                candidates = engine.build_candidates()
                fdr_result = fdr.annotate(candidates)
                for c in candidates:
                    c["pre_fdr_trade"] = bool(c.get("trade"))
                    c["trade"] = bool(c.get("fdr_selected"))

                # Query UCB must receive the outcomes of the scoring stage. In the
                # old daemon it only saw scans/failures, so it was not adaptive to
                # economic signal quality at all.
                scheduler_error = _record_scheduler_feedback(
                    args.tracking_db, candidates
                )

                # Existing inventory is evaluated first. Only a fresh executable
                # route can close a position; marks/comparable asks never do.
                engine.ledger.mark(candidates)
                closed = engine.ledger.apply_exit_policy()

                # Freed cash is immediately visible to the allocator. Newly opened
                # positions cannot close in the same cycle because the exit policy
                # already ran above.
                basket = engine.allocate(candidates)
                engine.record_cycle(counts, candidates, len(fdr_result.selected))
                payload = engine.dashboard_payload(candidates, basket)
                ledger_summary = engine.ledger.summary()
                payload["cycle_rows"] = counts
                payload["closed_this_cycle"] = closed
                payload["realized_pnl"] = ledger_summary.realized_pnl
                payload["aged_capital"] = ledger_summary.aged_capital
                payload["scheduler_error"] = scheduler_error
                payload["posterior_fdr"] = {
                    "alpha": fdr_result.alpha,
                    "mean_false_probability": fdr_result.mean_false_probability,
                    "selected": len(fdr_result.selected),
                }
                payload["experiment"]["target_hours"] = (
                    args.max_hours if args.max_hours > 0 else 48.0
                )
                payload["experiment"]["label"] = (
                    f"{args.max_hours:g}H DIAGNOSTIC SHADOW"
                    if args.max_hours > 0
                    else "OPEN SHADOW"
                )
                Path(args.dashboard).parent.mkdir(parents=True, exist_ok=True)
                Path(args.dashboard).write_text(
                    json.dumps(
                        normalize_payload(payload), indent=2, ensure_ascii=False
                    )
                )
                with state.lock:
                    state.payload = payload
                    state.error = ""

                feed_errors = {
                    k: str(v.get("error") or "")[:160]
                    for k, v in engine.feed_state.items()
                    if v.get("error")
                }
                print(
                    json.dumps(
                        {
                            "status": payload.get("status"),
                            "rows": counts,
                            "feed_errors": feed_errors,
                            "scheduler_error": scheduler_error,
                            "raw": len(candidates),
                            "pre_fdr": sum(
                                1 for c in candidates if c.get("pre_fdr_trade")
                            ),
                            "fdr_selected": len(fdr_result.selected),
                            "opened": engine._last_new_positions,
                            "closed": len(closed),
                            "open_positions": payload.get("open_positions"),
                            "deployed": payload.get("deployed"),
                            "cash": payload.get("cash"),
                            "realized_pnl": payload.get("realized_pnl"),
                            "mark_pnl": payload.get("mark_pnl"),
                            "aged_capital": payload.get("aged_capital"),
                            "pca": payload.get("model_status", {}).get(
                                "PCA residual factors"
                            ),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            except Exception as e:
                with state.lock:
                    state.error = str(e)[:500]
                    state.payload = dict(
                        state.payload, status="ERROR", error=state.error
                    )
                print(f"cycle error: {e}", flush=True)

            if args.once or (deadline is not None and time.time() >= deadline):
                break
            time.sleep(max(1, args.interval - int(time.time() - t0)))
    finally:
        with state.lock:
            state.payload = dict(state.payload, status="SHADOW-COMPLETE")
        Path(args.dashboard).parent.mkdir(parents=True, exist_ok=True)
        Path(args.dashboard).write_text(
            json.dumps(normalize_payload(state.payload), indent=2, ensure_ascii=False)
        )
        engine.close()
        server.shutdown()


if __name__ == "__main__":
    main()
