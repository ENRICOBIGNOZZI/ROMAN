from __future__ import annotations

import hashlib
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DDL = """
CREATE TABLE IF NOT EXISTS query_stats (
  source TEXT NOT NULL, query TEXT NOT NULL, scans INTEGER NOT NULL DEFAULT 0,
  rows_seen INTEGER NOT NULL DEFAULT 0, signals INTEGER NOT NULL DEFAULT 0,
  selected INTEGER NOT NULL DEFAULT 0, reward_sum REAL NOT NULL DEFAULT 0,
  last_scan TEXT, PRIMARY KEY(source,query)
);
CREATE TABLE IF NOT EXISTS query_candidate_rewards (
  source TEXT NOT NULL, query TEXT NOT NULL, candidate_fingerprint TEXT NOT NULL,
  first_rewarded_at TEXT NOT NULL, reward REAL NOT NULL, selected INTEGER NOT NULL,
  PRIMARY KEY(source,query,candidate_fingerprint)
);
CREATE TABLE IF NOT EXISTS query_forward_stats (
  source TEXT NOT NULL, query TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 0,
  wins INTEGER NOT NULL DEFAULT 0, reward_sum REAL NOT NULL DEFAULT 0,
  last_outcome TEXT, PRIMARY KEY(source,query)
);
CREATE TABLE IF NOT EXISTS query_outcome_rewards (
  source TEXT NOT NULL, query TEXT NOT NULL, position_id TEXT NOT NULL,
  horizon_hours INTEGER NOT NULL, rewarded_at TEXT NOT NULL, reward REAL NOT NULL,
  success INTEGER NOT NULL, PRIMARY KEY(source,query,position_id,horizon_hours)
);
CREATE TABLE IF NOT EXISTS query_failures (
  source TEXT NOT NULL, query TEXT NOT NULL, failures INTEGER NOT NULL DEFAULT 0,
  last_error TEXT, last_error_at TEXT, PRIMARY KEY(source,query)
);
"""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(c: dict) -> str:
    raw = "|".join(
        [
            str(c.get("entity_key", "")),
            str(c.get("buy_external_id", "")),
            str(c.get("exit_source", "")),
        ]
    )
    return hashlib.sha1(raw.encode()).hexdigest()[:24]


def _finite(x, default: float = 0.0) -> float:
    try:
        v = float(x)
        return v if math.isfinite(v) else float(default)
    except Exception:
        return float(default)


class AdaptiveQueryScheduler:
    """UCB allocation of scarce API calls with deduplicated signal rewards."""

    def __init__(
        self,
        db_path: str = "data/roman_tracking.sqlite",
        exploration: float = 0.65,
    ):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(DDL)
        self.exploration = float(exploration)

    def close(self):
        self.db.commit()
        self.db.close()

    def choose(self, source: str, queries: list[str], n: int) -> list[str]:
        if not queries or n <= 0:
            return []
        rows = {
            r["query"]: r
            for r in self.db.execute(
                "SELECT * FROM query_stats WHERE source=?", (source,)
            )
        }
        fwd = {
            r["query"]: r
            for r in self.db.execute(
                "SELECT * FROM query_forward_stats WHERE source=?", (source,)
            )
        }
        fails = {
            r["query"]: r
            for r in self.db.execute(
                "SELECT * FROM query_failures WHERE source=?", (source,)
            )
        }
        total = sum(int(r["scans"]) for r in rows.values()) + 1
        now = datetime.now(timezone.utc)
        scored = []
        for q in queries:
            r = rows.get(q)
            fr = fwd.get(q)
            if r is None or int(r["scans"]) == 0:
                score = 1e6
            else:
                scans = int(r["scans"])
                signal_mean = _finite(r["reward_sum"]) / max(scans, 1)
                fn = int(fr["n"]) if fr is not None else 0
                fmean = _finite(fr["reward_sum"]) / fn if fn else 0.0
                shrink = fn / (fn + 8.0)
                mean = (1.0 - shrink) * signal_mean + shrink * fmean
                ucb = self.exploration * math.sqrt(math.log(total + 1.0) / scans)
                try:
                    last = datetime.fromisoformat(
                        str(r["last_scan"]).replace("Z", "+00:00")
                    )
                    age_h = max(0.0, (now - last).total_seconds() / 3600)
                except Exception:
                    age_h = 24.0
                freshness = min(0.20, age_h / 240.0)
                fail = fails.get(q)
                failures = int(fail["failures"]) if fail is not None else 0
                failure_penalty = min(3.0, 0.40 * failures / max(scans, 1))
                score = mean * 1e5 + ucb + freshness - failure_penalty
            scored.append((score, q))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [q for _, q in scored[: min(n, len(scored))]]

    def record_scan(self, source: str, query: str, rows: int) -> None:
        self.db.execute(
            """INSERT INTO query_stats(source,query,scans,rows_seen,last_scan)
               VALUES (?,?,1,?,?)
               ON CONFLICT(source,query) DO UPDATE SET
                 scans=query_stats.scans+1,
                 rows_seen=query_stats.rows_seen+excluded.rows_seen,
                 last_scan=excluded.last_scan""",
            (source, query, int(rows), _now()),
        )
        self.db.commit()

    def record_error(self, source: str, query: str, error: str) -> None:
        now = _now()
        self.db.execute(
            """INSERT INTO query_stats(source,query,scans,rows_seen,last_scan)
               VALUES (?,?,1,0,?)
               ON CONFLICT(source,query) DO UPDATE SET
                 scans=query_stats.scans+1,last_scan=excluded.last_scan""",
            (source, query, now),
        )
        self.db.execute(
            """INSERT INTO query_failures(source,query,failures,last_error,last_error_at)
               VALUES (?,?,1,?,?)
               ON CONFLICT(source,query) DO UPDATE SET
                 failures=query_failures.failures+1,
                 last_error=excluded.last_error,
                 last_error_at=excluded.last_error_at""",
            (source, query, str(error)[:500], now),
        )
        self.db.commit()

    def record_candidates(self, candidates: list[dict]) -> None:
        """Feed scored live candidates back into query allocation exactly once."""
        for c in candidates:
            source = str(c.get("buy_source") or "")
            query = str(c.get("buy_query") or "")
            if not source or not query:
                continue
            fp = _fingerprint(c)
            reward = max(0.0, _finite(c.get("score_per_capital_day"), 0.0))
            selected = int(bool(c.get("fdr_selected")))
            cur = self.db.execute(
                """INSERT OR IGNORE INTO query_candidate_rewards(
                       source,query,candidate_fingerprint,first_rewarded_at,reward,selected
                   ) VALUES (?,?,?,?,?,?)""",
                (source, query, fp, _now(), reward, selected),
            )
            if cur.rowcount:
                self.db.execute(
                    """INSERT INTO query_stats(
                           source,query,signals,selected,reward_sum,last_scan
                       ) VALUES (?,?,1,?,?,?)
                       ON CONFLICT(source,query) DO UPDATE SET
                         signals=query_stats.signals+1,
                         selected=query_stats.selected+excluded.selected,
                         reward_sum=query_stats.reward_sum+excluded.reward_sum""",
                    (source, query, selected, reward, _now()),
                )
        self.db.commit()

    def record_forward_outcomes(self, horizons: tuple[int, ...] = (24, 48)) -> int:
        """Consume an optional legacy forward-outcome schema when it is present.

        The standard ROMAN tracking database does not own shadow positions or
        decisions. Older code queried those tables unconditionally and crashed
        with ``no such table``. Until the cross-database forward-calibration layer
        is implemented, this method is safely inert on the standard schema.
        """
        if not horizons:
            return 0
        tables = {
            str(r[0])
            for r in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        required = {"horizon_outcomes", "shadow_positions", "decisions"}
        if not required.issubset(tables):
            return 0

        marks = ",".join("?" for _ in horizons)
        sql = f"""
          SELECT o.position_id,o.horizon_hours,o.actual_mark_profit,o.success,
                 p.entry_cost,p.candidate_id
          FROM horizon_outcomes o JOIN shadow_positions p ON p.position_id=o.position_id
          WHERE o.horizon_hours IN ({marks})
          ORDER BY o.evaluated_at
        """
        rewarded = 0
        for o in self.db.execute(sql, tuple(int(h) for h in horizons)):
            d = self.db.execute(
                """SELECT buy_source,raw_json FROM decisions
                   WHERE candidate_id=? AND basket_selected=1
                   ORDER BY observed_at LIMIT 1""",
                (o["candidate_id"],),
            ).fetchone()
            if d is None:
                continue
            try:
                import json

                raw = json.loads(d["raw_json"] or "{}")
            except Exception:
                raw = {}
            source = str(d["buy_source"] or raw.get("buy_source") or "")
            query = str(raw.get("buy_query") or "")
            if not source or not query:
                continue
            horizon = int(o["horizon_hours"])
            entry = max(_finite(o["entry_cost"]), 1e-9)
            days = max(horizon / 24.0, 1.0)
            raw_reward = _finite(o["actual_mark_profit"]) / (entry * days)
            weight = 0.35 if horizon <= 24 else 0.65
            reward = weight * raw_reward
            cur = self.db.execute(
                """INSERT OR IGNORE INTO query_outcome_rewards(
                       source,query,position_id,horizon_hours,rewarded_at,reward,success
                   ) VALUES (?,?,?,?,?,?,?)""",
                (
                    source,
                    query,
                    o["position_id"],
                    horizon,
                    _now(),
                    reward,
                    int(o["success"] or 0),
                ),
            )
            if not cur.rowcount:
                continue
            self.db.execute(
                """INSERT INTO query_forward_stats(
                       source,query,n,wins,reward_sum,last_outcome
                   ) VALUES (?,?,1,?,?,?)
                   ON CONFLICT(source,query) DO UPDATE SET
                     n=query_forward_stats.n+1,
                     wins=query_forward_stats.wins+excluded.wins,
                     reward_sum=query_forward_stats.reward_sum+excluded.reward_sum,
                     last_outcome=excluded.last_outcome""",
                (source, query, int(o["success"] or 0), reward, _now()),
            )
            self.db.execute(
                """INSERT OR IGNORE INTO query_stats(
                       source,query,scans,rows_seen,signals,selected,reward_sum,last_scan
                   ) VALUES (?,?,0,0,0,0,0,?)""",
                (source, query, _now()),
            )
            rewarded += 1
        self.db.commit()
        return rewarded

    def leaderboard(self, limit: int = 50) -> list[dict]:
        q = """SELECT q.source,q.query,q.scans,q.rows_seen,q.signals,q.selected,q.reward_sum,
                    CASE WHEN q.scans>0 THEN q.reward_sum/q.scans ELSE 0 END signal_reward_per_scan,
                    COALESCE(f.n,0) forward_n,COALESCE(f.wins,0) forward_wins,
                    CASE WHEN COALESCE(f.n,0)>0 THEN f.reward_sum/f.n ELSE 0 END forward_reward_mean,
                    q.last_scan,f.last_outcome,COALESCE(x.failures,0) failures,x.last_error_at
             FROM query_stats q LEFT JOIN query_forward_stats f
               ON f.source=q.source AND f.query=q.query
             LEFT JOIN query_failures x
               ON x.source=q.source AND x.query=q.query
             ORDER BY forward_n DESC,forward_reward_mean DESC,
                      signal_reward_per_scan DESC,q.selected DESC LIMIT ?"""
        return [dict(r) for r in self.db.execute(q, (int(limit),))]
