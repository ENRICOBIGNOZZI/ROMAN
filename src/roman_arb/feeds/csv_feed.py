from __future__ import annotations
import csv
from pathlib import Path
from .base import RawListing


class CSVFeed:
    """Universal safe adapter for exports/partner feeds/manual snapshots.

    Required columns: external_id,title,price,currency.
    Optional: url,condition,seller,category,product_key,observed_at.
    """
    def __init__(self, source: str, path: str | Path):
        self.name = source
        self.path = Path(path)

    def available(self) -> bool:
        return self.path.exists()

    def fetch(self, query: str = "", limit: int = 10000):
        out=[]
        with self.path.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if query and query.lower() not in (row.get("title") or "").lower():
                    continue
                out.append(RawListing(
                    source=self.name,
                    external_id=str(row.get("external_id") or row.get("id") or len(out)+1),
                    title=row.get("title", ""),
                    price=float(row.get("price", 0) or 0),
                    currency=row.get("currency", "EUR"),
                    url=row.get("url", ""),
                    condition=row.get("condition", ""),
                    seller=row.get("seller", ""),
                    category=row.get("category", ""),
                    product_key=row.get("product_key", ""),
                    observed_at=row.get("observed_at", ""),
                    extra={k:v for k,v in row.items() if k not in {"external_id","id","title","price","currency","url","condition","seller","category","product_key","observed_at"}},
                ))
                if len(out)>=limit: break
        return out
