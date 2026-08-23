from __future__ import annotations

import os
import threading
import time
from urllib.parse import urlencode

from .base import RawListing
from .http_utils import get_json


class PriceChartingFeed:
    """Licensed PriceCharting videogame marketplace/price-guide adapter.

    The API documents a one-request-per-second limit.  Marketplace offers are
    preferred because they represent actual available listings.  If no offer is
    returned for the best product match, the price guide is emitted only as a
    ``reference_only`` observation and can never be selected as an executable
    route or acquisition listing by the live engine.
    """

    name = "pricecharting"

    def __init__(self, token: str | None = None, max_products: int = 2):
        self.token = token or os.getenv("PRICECHARTING_TOKEN", "")
        self.max_products = max(1, min(int(max_products), 5))
        self._lock = threading.Lock()
        self._last_call = 0.0

    def available(self):
        return bool(self.token)

    def _call(self, path: str, **params):
        with self._lock:
            elapsed = time.monotonic() - self._last_call
            if elapsed < 1.02:
                time.sleep(1.02 - elapsed)
            params["t"] = self.token
            url = f"https://www.pricecharting.com{path}?{urlencode(params)}"
            data = get_json(url, retries=1)
            self._last_call = time.monotonic()
        if isinstance(data, dict) and data.get("status") == "error":
            raise RuntimeError(str(data.get("error-message") or "PriceCharting API error"))
        return data

    @staticmethod
    def _reference_rows(product: dict, detail: dict, query: str) -> list[RawListing]:
        pid = str(product.get("id") or detail.get("id") or "")
        title = str(detail.get("product-name") or product.get("product-name") or query)
        console = str(detail.get("console-name") or product.get("console-name") or "")
        out = []
        for field, label in (
            ("loose-price", "Loose"),
            ("cib-price", "CIB"),
            ("new-price", "New & Sealed"),
        ):
            try:
                pennies = int(detail.get(field) or 0)
            except Exception:
                pennies = 0
            if pennies <= 0:
                continue
            out.append(
                RawListing(
                    source="pricecharting",
                    external_id=f"guide:{pid}:{field}",
                    title=f"{title} {console}".strip(),
                    price=pennies / 100.0,
                    currency="USD",
                    url=f"https://www.pricecharting.com/game/{pid}" if pid else "",
                    condition=label,
                    category=f"Video Games / {console}".strip(" /"),
                    product_key=f"pc:{pid}" if pid else "",
                    extra={
                        "query": query,
                        "product_id": pid,
                        "reference_only": True,
                        "reference_kind": "price_guide",
                        "executable_confidence": 0.12,
                        "source_market": "pricecharting",
                    },
                )
            )
        return out

    def fetch(self, query: str, limit: int = 50):
        if not self.available():
            return []
        products_data = self._call("/api/products", q=query)
        products = list((products_data or {}).get("products") or [])[: self.max_products]
        out: list[RawListing] = []
        for product in products:
            pid = str(product.get("id") or "")
            if not pid:
                continue
            offers_data = self._call(
                "/api/offers", status="available", id=pid, sort="lowest-price"
            )
            offers = list((offers_data or {}).get("offers") or [])
            for offer in offers:
                try:
                    pennies = int(offer.get("price") or 0)
                except Exception:
                    pennies = 0
                if pennies <= 0:
                    continue
                offer_id = str(offer.get("offer-id") or "")
                rel = str(offer.get("offer-url") or "")
                title = str(offer.get("product-name") or product.get("product-name") or query)
                console = str(offer.get("console-name") or product.get("console-name") or "")
                condition = " | ".join(
                    x
                    for x in (
                        str(offer.get("include-string") or ""),
                        str(offer.get("condition-string") or ""),
                    )
                    if x
                )
                out.append(
                    RawListing(
                        source=self.name,
                        external_id=offer_id or f"offer:{pid}:{len(out)}",
                        title=f"{title} {console}".strip(),
                        price=pennies / 100.0,
                        currency="USD",
                        url=("https://www.pricecharting.com" + rel) if rel.startswith("/") else rel,
                        condition=condition,
                        seller=str(offer.get("seller-id") or ""),
                        category=f"Video Games / {console}".strip(" /"),
                        product_key=f"pc:{pid}",
                        extra={
                            "query": query,
                            "product_id": pid,
                            "reference_only": False,
                            "executable_confidence": 0.55,
                            "source_market": "pricecharting",
                            "offer": offer,
                        },
                    )
                )
                if len(out) >= limit:
                    return out

            if not offers and len(out) < limit:
                detail = self._call("/api/product", id=pid)
                for row in self._reference_rows(product, detail or {}, query):
                    out.append(row)
                    if len(out) >= limit:
                        return out
        return out
