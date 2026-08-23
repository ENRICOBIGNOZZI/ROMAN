from __future__ import annotations
import os
from urllib.parse import quote_plus
from .base import RawListing
from .http_utils import get_json


class MercadoLibreFeed:
    """Read-only Mercado Libre listing search.

    The site search is a public read resource on several Mercado Libre sites.
    When a token is supplied we send it; otherwise the adapter attempts the
    public endpoint and gracefully reports an HTTP error if that site requires
    authentication.  No write/order endpoint is ever used.
    """

    def __init__(self, site_id: str = "MLM", source_name: str | None = None):
        self.token = os.getenv("MELI_ACCESS_TOKEN", "")
        self.site_id = str(site_id).upper()
        self.name = source_name or f"mercadolibre_{self.site_id.lower()}"

    def available(self):
        # Public read-only search can be attempted without an OAuth token.
        return True

    def fetch(self, query: str, limit: int = 50):
        url = (
            f"https://api.mercadolibre.com/sites/{self.site_id}/search"
            f"?q={quote_plus(query)}&limit={min(limit, 50)}"
        )
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        data = get_json(url, headers)
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
                    extra={**x, "site_id": self.site_id, "public_read": not bool(self.token)},
                )
            )
        return out
