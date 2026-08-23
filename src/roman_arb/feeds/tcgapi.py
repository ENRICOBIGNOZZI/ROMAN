from __future__ import annotations

import os
from urllib.parse import urlencode

from .base import RawListing
from .http_utils import get_json


class TCGReferenceFeed:
    """Licensed TCG pricing reference feed.

    The adapter intentionally requests sealed products only so the data maps to
    ROMAN's existing sealed-TCG sector. Returned rows are valuation references,
    not executable marketplace routes.
    """

    name = "tcgapi"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("TCGAPI_KEY", "")

    def available(self):
        return bool(self.api_key)

    def fetch(self, query: str, limit: int = 50):
        if not self.available():
            return []
        params = {
            "q": query,
            "type": "Sealed Products",
            "sort": "relevance",
            "page": 1,
            "per_page": min(max(int(limit), 1), 50),
        }
        data = get_json(
            "https://api.tcgapi.dev/v1/search?" + urlencode(params),
            {"X-API-Key": self.api_key},
            retries=1,
        )
        out: list[RawListing] = []
        for item in list((data or {}).get("data") or [])[:limit]:
            price = None
            for key in ("lowest_with_shipping", "low_price", "market_price", "price"):
                try:
                    x = float(item.get(key))
                except Exception:
                    continue
                if x > 0:
                    price = x
                    break
            if price is None:
                continue
            item_id = str(item.get("id") or item.get("tcgplayer_id") or "")
            set_name = str(item.get("set_name") or item.get("set") or "")
            name = str(item.get("name") or query)
            out.append(
                RawListing(
                    source=self.name,
                    external_id=f"ref:{item_id or len(out)}",
                    title=f"{name} {set_name}".strip(),
                    price=price,
                    currency="USD",
                    condition="Sealed",
                    category=f"Sealed TCG / {item.get('game_name') or item.get('game_slug') or ''}".strip(" /"),
                    product_key=(f"tcgapi:{item_id}" if item_id else ""),
                    extra={
                        "query": query,
                        "reference_only": True,
                        "reference_kind": "tcgapi_market_reference",
                        "executable_confidence": 0.12,
                        "total_listings": item.get("total_listings"),
                        "price_updated_at": item.get("price_updated_at"),
                        "tcg_item": item,
                    },
                )
            )
        return out
