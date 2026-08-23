from __future__ import annotations

import os
from urllib.parse import urlencode

from .base import RawListing
from .http_utils import get_json


_DOMAIN_CURRENCY = {
    1: "USD",
    2: "GBP",
    3: "EUR",
    4: "EUR",
    5: "JPY",
    6: "CAD",
    8: "EUR",
    9: "EUR",
    10: "INR",
    11: "MXN",
    12: "BRL",
}

_DOMAIN_HOST = {
    1: "amazon.com",
    2: "amazon.co.uk",
    3: "amazon.de",
    4: "amazon.fr",
    5: "amazon.co.jp",
    6: "amazon.ca",
    8: "amazon.it",
    9: "amazon.es",
    10: "amazon.in",
    11: "amazon.com.mx",
    12: "amazon.com.br",
}


class KeepaReferenceFeed:
    """Official Keepa Amazon reference-price adapter.

    Product Search can return current statistics without requesting marketplace
    offer refreshes. ROMAN uses Amazon/New/Used current prices as retail/reference
    evidence only; no Keepa row is an executable resale route.
    """

    name = "keepa_reference"

    def __init__(
        self,
        api_key: str | None = None,
        domain_id: int | None = None,
        max_products: int = 3,
    ):
        self.api_key = api_key or os.getenv("KEEPA_API_KEY", "")
        self.domain_id = int(
            domain_id
            if domain_id is not None
            else os.getenv("KEEPA_DOMAIN_ID", "3")
        )
        self.max_products = max(1, min(int(max_products), 10))

    def available(self):
        return bool(self.api_key and self.domain_id in _DOMAIN_CURRENCY)

    @staticmethod
    def _current_price(product: dict) -> tuple[int | None, str]:
        current = list(((product.get("stats") or {}).get("current") or []))
        # Keepa price type indices: 0=Amazon, 1=Marketplace New, 2=Used.
        for index, kind in ((0, "amazon"), (1, "new"), (2, "used")):
            if index >= len(current):
                continue
            try:
                value = int(current[index])
            except Exception:
                continue
            if value > 0:
                return value, kind
        return None, ""

    def fetch(self, query: str, limit: int = 50):
        if not self.available():
            return []
        params = {
            "key": self.api_key,
            "domain": self.domain_id,
            "type": "product",
            "term": query,
            "stats": 30,
            "history": 0,
            # Avoid spending refresh tokens: reference data need not be sub-hour.
            "update": 24,
        }
        data = get_json(
            "https://api.keepa.com/search?" + urlencode(params),
            {"Accept-Encoding": "gzip", "Accept": "application/json"},
            retries=1,
        )
        currency = _DOMAIN_CURRENCY[self.domain_id]
        host = _DOMAIN_HOST[self.domain_id]
        out: list[RawListing] = []
        for product in list((data or {}).get("products") or [])[: self.max_products]:
            cents, kind = self._current_price(product)
            if cents is None:
                continue
            asin = str(product.get("asin") or "")
            if not asin:
                continue
            title = str(product.get("title") or query)
            out.append(
                RawListing(
                    source=self.name,
                    external_id=f"{asin}:{kind}",
                    title=title,
                    price=cents / 100.0 if currency != "JPY" else float(cents),
                    currency=currency,
                    url=f"https://www.{host}/dp/{asin}",
                    condition=("Used" if kind == "used" else "New"),
                    category=str(product.get("websiteDisplayGroupName") or "Amazon reference"),
                    product_key=f"asin:{asin}",
                    extra={
                        "query": query,
                        "reference_only": True,
                        "reference_kind": f"keepa_{kind}",
                        "executable_confidence": 0.08,
                        "asin": asin,
                        "domain_id": self.domain_id,
                        "manufacturer": product.get("manufacturer"),
                        "brand": product.get("brand"),
                        "model": product.get("model"),
                        "keepa_stats": product.get("stats"),
                    },
                )
            )
            if len(out) >= limit:
                break
        return out
