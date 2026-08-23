from __future__ import annotations

import os
import re
import threading
import time
from urllib.parse import urlencode

from .base import RawListing
from .http_utils import get_json


_BRANDS = (
    "rolex",
    "omega",
    "cartier",
    "patek philippe",
    "audemars piguet",
    "breitling",
    "tudor",
    "tag heuer",
    "vacheron constantin",
    "grand seiko",
    "iwc",
    "panerai",
    "jaeger-lecoultre",
    "zenith",
    "seiko",
)


class WatchChartsReferenceFeed:
    """Official WatchCharts market-value reference feed.

    WatchCharts requires callers to provide brand + reference number. ROMAN does
    exactly that from its high-identity watch queries and uses only Level-1 market
    information as valuation evidence. No WatchCharts value can become a concrete
    buy or exit route.
    """

    name = "watchcharts_reference"
    base = "https://api.watchcharts.com/v3"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("WATCHCHARTS_API_KEY", "")
        self._lock = threading.Lock()
        self._last_call = 0.0

    def available(self):
        return bool(self.api_key)

    @staticmethod
    def _brand_reference(query: str) -> tuple[str, str] | None:
        text = (query or "").strip()
        low = text.lower()
        brand = next((b for b in _BRANDS if b in low), "")
        if not brand:
            return None
        remainder = low.replace(brand, " ", 1)
        candidates = re.findall(r"\b[a-z0-9][a-z0-9.\-/]{3,}\b", remainder)
        # Prefer an identifier containing digits and avoid generic model words.
        candidates = [x for x in candidates if any(ch.isdigit() for ch in x)]
        if not candidates:
            return None
        return brand, max(candidates, key=len)

    def _get(self, path: str, **params):
        with self._lock:
            elapsed = time.monotonic() - self._last_call
            if elapsed < 1.02:
                time.sleep(1.02 - elapsed)
            url = self.base + path + "?" + urlencode(params)
            data = get_json(url, {"x-api-key": self.api_key}, retries=1)
            self._last_call = time.monotonic()
            return data

    def fetch(self, query: str, limit: int = 50):
        if not self.available():
            return []
        parsed = self._brand_reference(query)
        if parsed is None:
            return []
        brand, reference = parsed
        search = self._get(
            "/search/watch",
            brand_name=brand,
            reference=reference,
            exact_match="true",
            include_no_data="true",
        )
        results = list((search or {}).get("results") or [])
        if not results:
            return []
        best = results[0]
        uuid = str(best.get("uuid") or "")
        if not uuid:
            return []
        info = self._get("/watch/info", uuid=uuid, currency="EUR") or {}
        values = []
        for field, kind, confidence in (
            ("market_price", "market_price", 0.18),
            ("median_asking_price", "median_asking_price", 0.12),
            ("dealer_price", "dealer_price", 0.10),
        ):
            try:
                price = float(info.get(field) or 0.0)
            except Exception:
                price = 0.0
            if price > 0:
                values.append((price, kind, confidence))

        out: list[RawListing] = []
        for price, kind, confidence in values[:limit]:
            model = str(info.get("model") or best.get("model") or reference)
            out.append(
                RawListing(
                    source=self.name,
                    external_id=f"{uuid}:{kind}",
                    title=f"{info.get('brand') or brand} {info.get('collection') or ''} {model}".strip(),
                    price=price,
                    currency="EUR",
                    url="https://watchcharts.com/",
                    condition="market reference",
                    category="Modern watches",
                    product_key=f"watchcharts:{uuid}",
                    extra={
                        "query": query,
                        "reference_only": True,
                        "reference_kind": f"watchcharts_{kind}",
                        "executable_confidence": confidence,
                        "watch_uuid": uuid,
                        "watch_reference": model,
                        "volatility": info.get("volatility"),
                        "updated": info.get("updated"),
                        "market_info": info,
                    },
                )
            )
        return out
