from __future__ import annotations
import os
from urllib.parse import quote_plus
from .base import RawListing
from .http_utils import get_json


class RakutenIchibaFeed:
    """Official Rakuten Ichiba Item Search API adapter."""
    name = "rakuten_ichiba"

    def __init__(self):
        self.application_id = os.getenv("RAKUTEN_APPLICATION_ID", "")
        self.access_key = os.getenv("RAKUTEN_ACCESS_KEY", "")

    def available(self):
        return bool(self.application_id and self.access_key)

    def fetch(self, query: str, limit: int = 30):
        hits = min(max(int(limit), 1), 30)
        url = (
            "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
            f"?applicationId={quote_plus(self.application_id)}"
            f"&accessKey={quote_plus(self.access_key)}"
            f"&keyword={quote_plus(query)}&hits={hits}&format=json&formatVersion=2"
        )
        data = get_json(url)
        out = []
        for x in data.get("items", []):
            out.append(RawListing(
                source=self.name,
                external_id=str(x.get("itemCode", "")),
                title=x.get("itemName", ""),
                price=float(x.get("itemPrice", 0) or 0),
                currency="JPY",
                url=x.get("itemUrl", ""),
                seller=x.get("shopName", ""),
                category=str(x.get("genreId", "")),
                extra=x,
            ))
        return out
