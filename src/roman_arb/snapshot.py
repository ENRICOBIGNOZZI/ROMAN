from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from .feeds.base import RawListing

DDL = """
CREATE TABLE IF NOT EXISTS listings (
  source TEXT NOT NULL, external_id TEXT NOT NULL, observed_at TEXT NOT NULL,
  title TEXT, price REAL, currency TEXT, url TEXT, condition TEXT, seller TEXT,
  category TEXT, product_key TEXT, extra_json TEXT,
  PRIMARY KEY(source, external_id, observed_at)
);
CREATE INDEX IF NOT EXISTS ix_listings_source_time ON listings(source, observed_at);
CREATE INDEX IF NOT EXISTS ix_listings_product_time ON listings(product_key, observed_at);

CREATE TABLE IF NOT EXISTS listing_state (
  source TEXT NOT NULL,
  external_id TEXT NOT NULL,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  seen_count INTEGER NOT NULL DEFAULT 1,
  first_price REAL,
  last_price REAL,
  min_price REAL,
  max_price REAL,
  PRIMARY KEY(source, external_id)
);
CREATE INDEX IF NOT EXISTS ix_listing_state_last_seen ON listing_state(last_seen);
"""


class SnapshotStore:
    def __init__(self, path="data/roman_snapshots.sqlite"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.executescript(DDL)

    def append(self, rows: list[RawListing]):
        if not rows:
            return
        values = [
            (
                r.source, r.external_id, r.observed_at, r.title, r.price, r.currency,
                r.url, r.condition, r.seller, r.category, r.product_key,
                json.dumps(r.extra, ensure_ascii=False),
            )
            for r in rows
        ]
        self.db.executemany("INSERT OR IGNORE INTO listings VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", values)
        for r in rows:
            self.db.execute(
                """
                INSERT INTO listing_state(source,external_id,first_seen,last_seen,seen_count,first_price,last_price,min_price,max_price)
                VALUES (?,?,?,?,1,?,?,?,?)
                ON CONFLICT(source,external_id) DO UPDATE SET
                  last_seen=excluded.last_seen,
                  seen_count=listing_state.seen_count+1,
                  last_price=excluded.last_price,
                  min_price=MIN(listing_state.min_price, excluded.last_price),
                  max_price=MAX(listing_state.max_price, excluded.last_price)
                """,
                (r.source, r.external_id, r.observed_at, r.observed_at, r.price, r.price, r.price, r.price),
            )
        self.db.commit()

    def count(self):
        return self.db.execute("SELECT COUNT(*) FROM listings").fetchone()[0]

    def close(self):
        self.db.close()
