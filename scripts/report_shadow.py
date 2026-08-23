from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


def _load_json(path: str):
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _drawdown(nav):
    peak = -math.inf
    worst = 0.0
    for x in nav:
        peak = max(peak, x)
        if peak > 0:
            worst = min(worst, x / peak - 1.0)
    return worst


def build_report(
    shadow_db="data/roman_shadow.sqlite",
    snapshot_db="data/roman_snapshots.sqlite",
    dashboard_path="outputs/live/dashboard.json",
):
    dash = _load_json(dashboard_path)
    report = {
        "brand": "Reselling BOT",
        "mode": "shadow diagnostic",
        "capital": float(dash.get("capital", 10000) or 10000),
        "status": dash.get("status", "unknown"),
        "model_status": dash.get("model_status", {}),
        "posterior_fdr": dash.get("posterior_fdr", {}),
    }

    p = Path(shadow_db)
    if not p.exists():
        report["error"] = "shadow ledger not found"
        return report
    db = sqlite3.connect(p)
    db.row_factory = sqlite3.Row
    cycles = [dict(r) for r in db.execute("SELECT * FROM shadow_cycles ORDER BY observed_at")]
    positions = [dict(r) for r in db.execute("SELECT * FROM shadow_positions ORDER BY entry_at")]
    db.close()

    feed_rows = Counter()
    reasons = Counter()
    for c in cycles:
        try:
            feed_rows.update(json.loads(c.get("rows_json") or "{}"))
        except Exception:
            pass
        try:
            reasons.update(json.loads(c.get("reason_json") or "{}"))
        except Exception:
            pass

    nav = [float(c.get("nav_mark") or report["capital"]) for c in cycles]
    deployed = [float(c.get("capital_deployed") or 0) for c in cycles]
    raw = [int(c.get("raw_candidates") or 0) for c in cycles]
    pre = [int(c.get("pre_fdr") or 0) for c in cycles]
    fdr = [int(c.get("fdr_selected") or 0) for c in cycles]
    new_pos = [int(c.get("new_positions") or 0) for c in cycles]

    duration_h = 0.0
    if len(cycles) >= 2:
        try:
            a = datetime.fromisoformat(cycles[0]["observed_at"].replace("Z", "+00:00"))
            b = datetime.fromisoformat(cycles[-1]["observed_at"].replace("Z", "+00:00"))
            duration_h = max(0.0, (b - a).total_seconds() / 3600)
        except Exception:
            pass

    snapshot_rows = 0
    unique_listings = 0
    sp = Path(snapshot_db)
    if sp.exists():
        sdb = sqlite3.connect(sp)
        snapshot_rows = int(sdb.execute("SELECT COUNT(*) FROM listings").fetchone()[0])
        unique_listings = int(
            sdb.execute("SELECT COUNT(*) FROM listing_state").fetchone()[0]
        )
        sdb.close()

    final_nav = nav[-1] if nav else report["capital"]
    final_deployed = deployed[-1] if deployed else 0.0
    final_cycle = cycles[-1] if cycles else {}
    report.update(
        {
            "duration_hours": duration_h,
            "cycles": len(cycles),
            "snapshot_rows": snapshot_rows,
            "unique_listings": unique_listings,
            "feed_rows": dict(feed_rows.most_common()),
            "candidate_funnel": {
                "raw_candidate_observations": sum(raw),
                "pre_fdr_trade_observations": sum(pre),
                "fdr_selected_observations": sum(fdr),
                "positions_opened": sum(new_pos),
                "final_open_positions": int(final_cycle.get("open_positions") or 0),
            },
            "capital": {
                "final_nav_mark": final_nav,
                "final_mark_pnl": final_nav - report["capital"],
                "max_drawdown_mark": _drawdown(nav),
                "average_deployed": sum(deployed) / len(deployed) if deployed else 0.0,
                "max_deployed": max(deployed) if deployed else 0.0,
                "final_deployed": final_deployed,
                "average_utilization": (
                    sum(deployed) / len(deployed) / report["capital"] if deployed else 0.0
                ),
                "final_executable_pnl": float(final_cycle.get("executable_pnl") or 0.0),
            },
            "decision_reasons": dict(reasons.most_common(30)),
            "positions": {
                "total_opened": len(positions),
                "locked_at_entry": sum(int(p.get("locked") or 0) for p in positions),
                "by_buy_source": dict(Counter(str(p.get("buy_source") or "") for p in positions)),
                "by_sector": dict(
                    Counter(
                        str((json.loads(p.get("meta_json") or "{}") or {}).get("sector") or "unknown")
                        for p in positions
                    )
                ),
            },
        }
    )

    strengths = []
    weaknesses = []
    active_feeds = [f for f in dash.get("feeds", []) if f.get("status") == "active"]
    if active_feeds:
        strengths.append(f"{len(active_feeds)} live read feeds returned data")
    else:
        weaknesses.append("no live feed was active; credentials/network are the first bottleneck")
    if snapshot_rows >= 500:
        strengths.append("enough raw observations were collected to audit matching and staleness")
    if sum(raw) == 0 and snapshot_rows > 0:
        weaknesses.append("listings were collected but cross-market entity matching produced no candidates")
    if sum(raw) > 0 and sum(pre) == 0:
        weaknesses.append("cross-market matches exist, but net costs/model agreement eliminate every trade")
    if sum(pre) > 0 and sum(fdr) == 0:
        weaknesses.append("model finds trades but posterior confidence is too low for the wide-universe FDR gate")
    if sum(fdr) > 0:
        strengths.append("at least one opportunity survived costs, ensemble gates and posterior FDR")
    util = report["capital"]["average_utilization"]
    if util < 0.15:
        weaknesses.append("capital is strongly opportunity-constrained at EUR 10k")
    elif util > 0.80:
        weaknesses.append("capital is near saturation; capacity/rationing matters already at EUR 10k")
    else:
        strengths.append("capital utilization is in a useful diagnostic range")
    if report["capital"]["final_executable_pnl"] == 0 and abs(report["capital"]["final_mark_pnl"]) > 0:
        weaknesses.append("positive/negative marks are not yet supported by executable exits")
    if str(report.get("model_status", {}).get("PCA residual factors", "")).upper() != "ONLINE":
        weaknesses.append("PCA did not accumulate enough stable temporal panel data during this run")
    if str(report.get("model_status", {}).get("Seller-quality posterior", "")).upper() in {"PRIOR", "WARMUP"}:
        weaknesses.append("seller-quality remains prior-driven; two hours are too short for genuine seller learning")

    total_feed = sum(feed_rows.values())
    if total_feed:
        dominant, n = feed_rows.most_common(1)[0]
        if n / total_feed > 0.80:
            weaknesses.append(f"data-source concentration is high: {dominant} supplied {n/total_feed:.0%} of rows")
    report["strengths"] = strengths
    report["weaknesses"] = weaknesses
    return report


def to_markdown(r: dict) -> str:
    cap = r.get("capital", {})
    fun = r.get("candidate_funnel", {})
    lines = [
        "# Reselling BOT — shadow diagnostic",
        "",
        f"- Duration: **{r.get('duration_hours', 0):.2f} h**",
        f"- Cycles: **{r.get('cycles', 0)}**",
        f"- Snapshot rows: **{r.get('snapshot_rows', 0):,}**",
        f"- Unique listings: **{r.get('unique_listings', 0):,}**",
        f"- Raw candidate observations: **{fun.get('raw_candidate_observations', 0)}**",
        f"- Pre-FDR trade observations: **{fun.get('pre_fdr_trade_observations', 0)}**",
        f"- FDR-selected observations: **{fun.get('fdr_selected_observations', 0)}**",
        f"- Positions opened: **{fun.get('positions_opened', 0)}**",
        f"- Final mark NAV: **EUR {cap.get('final_nav_mark', 0):,.2f}**",
        f"- Final shadow mark P&L: **EUR {cap.get('final_mark_pnl', 0):,.2f}**",
        f"- Executable-exit P&L evidence: **EUR {cap.get('final_executable_pnl', 0):,.2f}**",
        f"- Average utilization: **{100*cap.get('average_utilization', 0):.1f}%**",
        f"- Max mark drawdown: **{100*cap.get('max_drawdown_mark', 0):.2f}%**",
        "",
        "## Strengths",
    ]
    lines += [f"- {x}" for x in r.get("strengths", [])] or ["- None established yet."]
    lines += ["", "## Weaknesses"]
    lines += [f"- {x}" for x in r.get("weaknesses", [])] or ["- None detected by automatic rules."]
    lines += ["", "## Decision reasons"]
    for k, v in list(r.get("decision_reasons", {}).items())[:20]:
        lines.append(f"- `{k}`: {v}")
    lines += ["", "## Feed rows"]
    for k, v in r.get("feed_rows", {}).items():
        lines.append(f"- `{k}`: {v:,}")
    lines.append("")
    lines.append("> Mark P&L is not realized P&L. Only fresh executable bids are counted as executable-exit evidence.")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--shadow-db", default="data/roman_shadow.sqlite")
    p.add_argument("--snapshot-db", default="data/roman_snapshots.sqlite")
    p.add_argument("--dashboard", default="outputs/live/dashboard.json")
    p.add_argument("--out", default="outputs/live/diagnostic_report")
    args = p.parse_args()
    r = build_report(args.shadow_db, args.snapshot_db, args.dashboard)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(r, indent=2, ensure_ascii=False))
    out.with_suffix(".md").write_text(to_markdown(r))
    print(to_markdown(r))


if __name__ == "__main__":
    main()
