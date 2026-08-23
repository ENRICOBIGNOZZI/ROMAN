from __future__ import annotations

import os
from urllib.parse import quote_plus

from .base import RawListing
from .http_utils import get_json


class MercadoLibreFeed:
    """Read-only Mercado Libre listing search using an OAuth access token.

    ROMAN used to attempt this endpoint anonymously. The network smoke showed the
    current endpoint returning authorization errors, so the adapter now fails
    closed as ``NO_CREDENTIALS`` instead of repeatedly treating auth failures as a
    live-data test. No write/order endpoint is used.
    """

    def __init__(self, site_id: str = "MLM", source_name: str | None = None):
        self.token = os.getenv("MELI_ACCESS_TOKEN", "")
        self.site_id = str(site_id).upper()
        self.name = source_name or f"mercadolibre_{self.site_id.lower()}"

    def available(self):
        return bool(self.token)

    def fetch(self, query: str, limit: int = 50):
        url = (
            f"https://api.mercadolibre.com/sites/{self.site_id}/search"
            f"?q={quote_plus(query)}&limit={min(limit, 50)}"
        )
        data = get_json(url, {"Authorization": f"Bearer {self.token}"})
        out = []
        for x in data.get("results", []):
            seller = x.get("seller")
            seller_name = seller.get("nickname", "") if isinstance(seller, dict) else ""
            out.append(
                RawListing(
                    source=self.name,
                    external_id=str(x.get("id", "")),
                    title=x.get("title", ""),
                    price=float(x.get("price", 0) or 0),
                    currency=x.get("currency_id", ""),
                    url=x.get("permalink", ""),
                    condition=x.get("condition", ""),
                    seller=str(seller_name),
                    category=x.get("category_id", ""),
                    product_key=str(x.get("catalog_product_id") or ""),
                    extra={**x, "site_id": self.site_id, "authenticated_read": True},
                )
            )
        return out
