from __future__ import annotations

import os
from urllib.parse import urlencode

from .base import RawListing
from .http_utils import get_json


class DiscogsReferenceFeed:
    """Discogs official API reference-price adapter for vinyl/music releases.

    Global release search plus marketplace stats are used as valuation evidence.
    The stats endpoint exposes the lowest marketplace price and number for sale,
    but not a concrete globally-searchable listing route, so rows are explicitly
    ``reference_only``.
    """

    name = "discogs"

    def __init__(self, token: str | None = None, max_releases: int = 4):
        self.token = token or os.getenv("DISCOGS_TOKEN", "")
        self.max_releases = max(1, min(int(max_releases), 10))

    def available(self):
        return bool(self.token)

    def _headers(self):
        return {
            "Authorization": f"Discogs token={self.token}",
            "User-Agent": "ROMAN-Resale-Research/1.0",
            "Accept": "application/json",
        }

    def fetch(self, query: str, limit: int = 50):
        if not self.available():
            return []
        search_url = "https://api.discogs.com/database/search?" + urlencode(
            {
                "q": query,
                "type": "release",
                "per_page": min(self.max_releases, limit, 10),
                "page": 1,
            }
        )
        data = get_json(search_url, self._headers(), retries=1)
        releases = list((data or {}).get("results") or [])[: self.max_releases]
        out: list[RawListing] = []
        for release in releases:
            rid = str(release.get("id") or "")
            if not rid:
                continue
            stats = get_json(
                f"https://api.discogs.com/marketplace/stats/{rid}?curr_abbr=EUR",
                self._headers(),
                retries=1,
            )
            lowest = (stats or {}).get("lowest_price") or {}
            try:
                if isinstance(lowest, dict):
                    price = float(lowest.get("value") or 0.0)
                    currency = str(lowest.get("currency") or "EUR")
                else:
                    price = float(lowest or 0.0)
                    currency = "EUR"
            except Exception:
                price, currency = 0.0, "EUR"
            if price <= 0:
                continue
            uri = str(release.get("uri") or "")
            out.append(
                RawListing(
                    source=self.name,
                    external_id=f"stats:{rid}",
                    title=str(release.get("title") or query),
                    price=price,
                    currency=currency,
                    url=("https://www.discogs.com" + uri) if uri.startswith("/") else uri,
                    condition="marketplace lowest price",
                    category="Rare vinyl",
                    product_key=f"discogs:{rid}",
                    extra={
                        "query": query,
                        "release_id": rid,
                        "num_for_sale": (stats or {}).get("num_for_sale"),
                        "blocked_from_sale": (stats or {}).get("blocked_from_sale"),
                        "reference_only": True,
                        "reference_kind": "discogs_marketplace_stats",
                        "executable_confidence": 0.14,
                        "release": release,
                    },
                )
            )
            if len(out) >= limit:
                break
        return out
