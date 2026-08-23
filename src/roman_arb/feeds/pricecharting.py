from __future__ import annotations

import os
import threading
import time
from urllib.parse import urlencode

from .base import RawListing
from .http_utils import get_json


class PriceChartingFeed:
    """Licensed PriceCharting videogame marketplace/price-guide adapter.

    The API documents a one-request-per-second limit. Marketplace offers and
    price-guide references are independently switchable so the live execution
    pipeline never has to mix executable listings with valuation-only data.
    """

    name = "pricecharting"

    def __init__(
        self,
        token: str | None = None,
        max_products: int = 1,
        *,
        include_marketplace_offers: bool = True,
        include_reference_fallback: bool = False,
    ):
        self.token = token or os.getenv("PRICECHARTING_TOKEN", "")
        self.max_products = max(1, min(int(max_products), 5))
        self.include_marketplace_offers = bool(include_marketplace_offers)
        self.include_reference_fallback = bool(include_reference_fallback)
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
    def _global_key(detail: dict) -> str:
        upc = str(detail.get("upc") or "").strip()
        if upc:
            return f"gtin:{upc}"
        epid = str(detail.get("epid") or "").strip()
        if epid:
            return f"epid:{epid}"
        return ""

    @classmethod
    def _reference_rows(
        cls, product: dict, detail: dict, query: str
    ) -> list[RawListing]:
        pid = str(product.get("id") or detail.get("id") or "")
        title = str(detail.get("product-name") or product.get("product-name") or query)
        console = str(detail.get("console-name") or product.get("console-name") or "")
        global_key = cls._global_key(detail)
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
            extra = {
                "query": query,
                "product_id": pid,
                "reference_only": True,
                "reference_kind": "price_guide",
                "executable_confidence": 0.12,
                "source_market": "pricecharting",
            }
            if global_key:
                extra["global_product_key"] = global_key
            out.append(
                RawListing(
                    source="pricecharting_reference",
                    external_id=f"guide:{pid}:{field}",
                    title=f"{title} {console}".strip(),
                    price=pennies / 100.0,
                    currency="USD",
                    url=f"https://www.pricecharting.com/game/{pid}" if pid else "",
                    condition=label,
                    category=f"Video Games / {console}".strip(" /"),
                    product_key=global_key or (f"pc:{pid}" if pid else ""),
                    extra=extra,
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
            # Product details contain UPC/ePID identifiers that can link the same
            # physical game to eBay without fuzzy-title matching.
            detail = self._call("/api/product", id=pid)
            global_key = self._global_key(detail or {})
            offers = []
            if self.include_marketplace_offers:
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
                    title = str(
                        offer.get("product-name")
                        or detail.get("product-name")
                        or product.get("product-name")
                        or query
                    )
                    console = str(
                        offer.get("console-name")
                        or detail.get("console-name")
                        or product.get("console-name")
                        or ""
                    )
                    condition = " | ".join(
                        x
                        for x in (
                            str(offer.get("include-string") or ""),
                            str(offer.get("condition-string") or ""),
                        )
                        if x
                    )
                    extra = {
                        "query": query,
                        "product_id": pid,
                        "reference_only": False,
                        "executable_confidence": 0.55,
                        "source_market": "pricecharting",
                        "genre": detail.get("genre"),
                        "offer": offer,
                    }
                    if global_key:
                        extra["global_product_key"] = global_key
                    out.append(
                        RawListing(
                            source=self.name,
                            external_id=offer_id or f"offer:{pid}:{len(out)}",
                            title=f"{title} {console}".strip(),
                            price=pennies / 100.0,
                            currency="USD",
                            url=("https://www.pricecharting.com" + rel)
                            if rel.startswith("/")
                            else rel,
                            condition=condition,
                            seller=str(offer.get("seller-id") or ""),
                            category=f"Video Games / {console}".strip(" /"),
                            product_key=global_key or f"pc:{pid}",
                            extra=extra,
                        )
                    )
                    if len(out) >= limit:
                        return out

            if self.include_reference_fallback and (
                not offers or not self.include_marketplace_offers
            ):
                for row in self._reference_rows(product, detail or {}, query):
                    out.append(row)
                    if len(out) >= limit:
                        return out
        return out
