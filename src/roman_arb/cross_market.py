from __future__ import annotations
import json, sqlite3
from collections import defaultdict
from .entity import entity_key


def latest_rows(db_path="data/roman_snapshots.sqlite"):
    db=sqlite3.connect(db_path); db.row_factory=sqlite3.Row
    q="""
    SELECT l.* FROM listings l
    JOIN (SELECT source,external_id,MAX(observed_at) observed_at FROM listings GROUP BY source,external_id) z
      ON l.source=z.source AND l.external_id=z.external_id AND l.observed_at=z.observed_at
    WHERE price>0
    """
    rows=[dict(r) for r in db.execute(q)]; db.close(); return rows


def observed_cross_market_dispersion(db_path="data/roman_snapshots.sqlite", min_sources=2):
    groups=defaultdict(list)
    for r in latest_rows(db_path):
        k=entity_key(r)
        if k: groups[(k,r.get("currency") or "")].append(r)
    out=[]
    for (k,currency),rows in groups.items():
        if len({r['source'] for r in rows})<min_sources: continue
        lo=min(rows,key=lambda r:r['price']); hi=max(rows,key=lambda r:r['price'])
        if lo['price']<=0: continue
        out.append({
            "entity_key":k,"currency":currency,"sources":len({r['source'] for r in rows}),
            "low_source":lo['source'],"low_price":lo['price'],"low_url":lo.get('url',''),
            "high_source":hi['source'],"high_price":hi['price'],"high_url":hi.get('url',''),
            "raw_dispersion_pct":hi['price']/lo['price']-1,
            "warning":"Observed ask/listing dispersion only; not guaranteed executable arbitrage."
        })
    return sorted(out,key=lambda x:x['raw_dispersion_pct'],reverse=True)
