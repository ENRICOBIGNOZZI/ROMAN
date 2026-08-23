from __future__ import annotations

import json
import math
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse(x: str) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


DDL = """
CREATE TABLE IF NOT EXISTS shadow_positions (
  position_id TEXT PRIMARY KEY,
  entity_key TEXT NOT NULL,
  buy_external_id TEXT,
  buy_source TEXT,
  exit_source TEXT,
  entry_at TEXT NOT NULL,
  entry_cost REAL NOT NULL,
  entry_lcb_roi REAL,
  expected_days REAL,
  locked INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'OPEN',
  close_at TEXT,
  close_value REAL,
  close_reason TEXT,
  meta_json TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_open_entity
  ON shadow_positions(entity_key) WHERE status='OPEN';
CREATE TABLE IF NOT EXISTS shadow_marks (
  position_id TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  mark_value REAL,
  executable_value REAL,
  mark_pnl REAL,
  executable_pnl REAL,
  meta_json TEXT,
  PRIMARY KEY(position_id, observed_at)
);
CREATE TABLE IF NOT EXISTS shadow_cycles (
  observed_at TEXT PRIMARY KEY,
  rows_json TEXT,
  raw_candidates INTEGER,
  pre_fdr INTEGER,
  fdr_selected INTEGER,
  open_positions INTEGER,
  new_positions INTEGER,
  capital_deployed REAL,
  cash REAL,
  nav_mark REAL,
  mark_pnl REAL,
  executable_pnl REAL,
  reason_json TEXT
);
"""


@dataclass(frozen=True)
class LedgerSummary:
    cash: float
    deployed_cost: float
    nav_mark: float
    mark_pnl: float
    executable_pnl: float
    realized_pnl: float
    open_positions: int
    locked_positions: int
    aged_capital: float


class ShadowLedger:
    """Persistent paper ledger for a path-dependent shadow experiment.

    Marks are not realized P&L. A fresh executable bid is tracked separately.
    Positions can only close on executable evidence after a minimum physical
    settlement/transfer delay, never because a comparable ask moved higher.
    """

    def __init__(self, path: str = "data/roman_shadow.sqlite", capital: float = 10_000.0):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.capital = float(capital)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(DDL)

    def close(self):
        self.db.commit()
        self.db.close()

    def open_positions(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM shadow_positions WHERE status='OPEN' ORDER BY entry_at"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                meta = json.loads(d.get("meta_json") or "{}")
            except Exception:
                meta = {}
            d.update(meta)
            d["acquisition_cost"] = float(d["entry_cost"])
            out.append(d)
        return out

    def deployed_cost(self) -> float:
        row = self.db.execute(
            "SELECT COALESCE(SUM(entry_cost),0) FROM shadow_positions WHERE status='OPEN'"
        ).fetchone()
        return float(row[0] or 0.0)

    def realized_pnl(self) -> float:
        row = self.db.execute(
            "SELECT COALESCE(SUM(close_value-entry_cost),0) FROM shadow_positions WHERE status='CLOSED'"
        ).fetchone()
        return float(row[0] or 0.0)

    def cash(self) -> float:
        return self.capital + self.realized_pnl() - self.deployed_cost()

    def open_selected(self, selected: list[dict]) -> int:
        opened = 0
        existing = {r["entity_key"] for r in self.open_positions()}
        cash = self.cash()
        for c in selected:
            entity = str(c.get("entity_key") or "")
            cost = float(c.get("acquisition_cost") or 0.0)
            if not entity or entity in existing or cost <= 0 or cost > cash:
                continue
            pid = uuid.uuid4().hex[:20]
            meta = {
                "sector": c.get("sector"),
                "family": c.get("family"),
                "title": c.get("title"),
                "buy_url": c.get("buy_url"),
                "seller_route_key": c.get("seller_route_key"),
                "entry_confidence": c.get("ensemble_confidence"),
                "entry_reason": c.get("reason"),
                "cross_border": bool(c.get("cross_border")),
                # Physical resale cannot be instant. Cross-border inventory gets a
                # longer minimum settlement/availability delay.
                "min_exit_days": 3.0 if c.get("cross_border") else 1.0,
            }
            self.db.execute(
                """INSERT INTO shadow_positions(
                    position_id,entity_key,buy_external_id,buy_source,exit_source,
                    entry_at,entry_cost,entry_lcb_roi,expected_days,locked,meta_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    pid,
                    entity,
                    str(c.get("buy_external_id") or ""),
                    str(c.get("buy_source") or ""),
                    str(c.get("exit_source") or ""),
                    _now(),
                    cost,
                    float(c.get("lcb_net_roi") or 0.0),
                    float(c.get("expected_holding_days") or 365.0),
                    int(bool(c.get("locked"))),
                    json.dumps(meta, ensure_ascii=False),
                ),
            )
            existing.add(entity)
            cash -= cost
            opened += 1
        self.db.commit()
        return opened

    def mark(self, candidates: list[dict]) -> None:
        by_entity: dict[str, dict] = {}
        for c in candidates:
            e = str(c.get("entity_key") or "")
            if not e:
                continue
            prev = by_entity.get(e)
            if prev is None or float(c.get("score_per_capital_day") or -1e9) > float(prev.get("score_per_capital_day") or -1e9):
                by_entity[e] = c

        now = _now()
        for p in self.open_positions():
            c = by_entity.get(str(p["entity_key"]))
            if c is None:
                mark_value = float(p["entry_cost"])
                executable_value = None
                meta = {"reason": "no_fresh_candidate"}
            else:
                mark_value = max(0.0, float(c.get("expected_exit_net") or p["entry_cost"]))
                executable_value = None
                if c.get("locked_net_roi") is not None and bool(c.get("locked")):
                    executable_value = float(p["entry_cost"]) * (
                        1.0 + float(c.get("locked_net_roi") or 0.0)
                    )
                meta = {
                    "lcb_net_roi": c.get("lcb_net_roi"),
                    "confidence": c.get("ensemble_confidence"),
                    "reason": c.get("reason"),
                }
            entry = float(p["entry_cost"])
            self.db.execute(
                "INSERT OR REPLACE INTO shadow_marks VALUES (?,?,?,?,?,?,?)",
                (
                    str(p["position_id"]),
                    now,
                    mark_value,
                    executable_value,
                    mark_value - entry,
                    (executable_value - entry) if executable_value is not None else None,
                    json.dumps(meta, ensure_ascii=False),
                ),
            )
        self.db.commit()

    def latest_mark(self, position_id: str) -> tuple[float | None, float | None]:
        r = self.db.execute(
            """SELECT mark_value,executable_value FROM shadow_marks
               WHERE position_id=? ORDER BY observed_at DESC LIMIT 1""",
            (position_id,),
        ).fetchone()
        if r is None:
            return None, None
        return (
            float(r[0]) if r[0] is not None else None,
            float(r[1]) if r[1] is not None else None,
        )

    def apply_exit_policy(
        self,
        min_take_profit_roi: float = 0.003,
        max_initial_target_roi: float = 0.015,
        hard_age_days: float = 45.0,
    ) -> list[dict]:
        """Close paper positions only against fresh executable evidence.

        Profit target decays with inventory age. Once expected holding time is
        reached, any non-negative executable exit is accepted to recycle capital.
        Very aged inventory can accept a small loss, but an ask/mark alone can
        never trigger a close.
        """
        now = datetime.now(timezone.utc)
        closed = []
        for p in self.open_positions():
            entry_dt = _parse(str(p.get("entry_at") or ""))
            if entry_dt is None:
                continue
            age_days = max(0.0, (now - entry_dt).total_seconds() / 86400.0)
            min_exit_days = max(0.0, float(p.get("min_exit_days") or 1.0))
            if age_days < min_exit_days:
                continue
            _, exe = self.latest_mark(str(p["position_id"]))
            if exe is None or exe <= 0:
                continue
            entry = float(p["entry_cost"])
            roi = float(exe) / max(entry, 1e-9) - 1.0
            expected = max(1.0, float(p.get("expected_days") or 30.0))
            entry_lcb = max(0.0, float(p.get("entry_lcb_roi") or 0.0))
            initial_target = min(max_initial_target_roi, max(min_take_profit_roi, 0.5 * entry_lcb))
            target = max(
                min_take_profit_roi,
                initial_target * math.exp(-age_days / expected),
            )

            reason = None
            if roi >= target:
                reason = "take_profit_executable"
            elif age_days >= expected and roi >= 0.0:
                reason = "recycle_at_expected_horizon"
            elif age_days >= 2.0 * expected and roi >= -0.02:
                reason = "aged_inventory_recycle"
            elif age_days >= hard_age_days and roi >= -0.05:
                reason = "hard_age_recycle"

            if reason is None:
                continue
            self.db.execute(
                """UPDATE shadow_positions SET status='CLOSED',close_at=?,close_value=?,close_reason=?
                   WHERE position_id=? AND status='OPEN'""",
                (_now(), float(exe), reason, str(p["position_id"])),
            )
            closed.append(
                {
                    "position_id": str(p["position_id"]),
                    "entity_key": str(p["entity_key"]),
                    "entry_cost": entry,
                    "close_value": float(exe),
                    "roi": roi,
                    "age_days": age_days,
                    "reason": reason,
                }
            )
        self.db.commit()
        return closed

    def summary(self) -> LedgerSummary:
        positions = self.open_positions()
        deployed = sum(float(p["entry_cost"]) for p in positions)
        cash = self.cash()
        mark_total = 0.0
        exec_pnl = 0.0
        locked = 0
        aged_capital = 0.0
        now = datetime.now(timezone.utc)
        for p in positions:
            mark, exe = self.latest_mark(str(p["position_id"]))
            mark_total += float(mark if mark is not None else p["entry_cost"])
            if exe is not None:
                exec_pnl += float(exe) - float(p["entry_cost"])
                locked += 1
            entry_dt = _parse(str(p.get("entry_at") or ""))
            if entry_dt is not None:
                age = max(0.0, (now - entry_dt).total_seconds() / 86400.0)
                expected = max(1.0, float(p.get("expected_days") or 30.0))
                if age >= min(14.0, 0.75 * expected):
                    aged_capital += float(p["entry_cost"])
        nav = cash + mark_total
        return LedgerSummary(
            cash=cash,
            deployed_cost=deployed,
            nav_mark=nav,
            mark_pnl=nav - self.capital,
            executable_pnl=exec_pnl,
            realized_pnl=self.realized_pnl(),
            open_positions=len(positions),
            locked_positions=locked,
            aged_capital=aged_capital,
        )

    def log_cycle(
        self,
        *,
        rows: dict,
        raw_candidates: int,
        pre_fdr: int,
        fdr_selected: int,
        new_positions: int,
        reasons: dict[str, int],
    ) -> None:
        s = self.summary()
        self.db.execute(
            "INSERT OR REPLACE INTO shadow_cycles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                _now(),
                json.dumps(rows, ensure_ascii=False),
                int(raw_candidates),
                int(pre_fdr),
                int(fdr_selected),
                int(s.open_positions),
                int(new_positions),
                float(s.deployed_cost),
                float(s.cash),
                float(s.nav_mark),
                float(s.mark_pnl),
                float(s.executable_pnl),
                json.dumps(reasons, ensure_ascii=False),
            ),
        )
        self.db.commit()

    def nav_series(self, limit: int = 1000) -> list[dict]:
        rows = self.db.execute(
            "SELECT observed_at,nav_mark,mark_pnl FROM shadow_cycles ORDER BY observed_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [
            {
                "t": r["observed_at"],
                "nav": float(r["nav_mark"]),
                "mark_pnl": float(r["mark_pnl"]),
            }
            for r in reversed(rows)
        ]
