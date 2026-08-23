from __future__ import annotations

import os
import time
from urllib.error import HTTPError
from urllib.parse import quote_plus

from .base import RawListing
from .http_utils import basic_auth, get_json, post_form_json


class EbayBrowseFeed:
    name = "ebay"

    def __init__(self, marketplace: str = "EBAY_CH"):
        self.client_id = os.getenv("EBAY_CLIENT_ID", "")
        self.secret = os.getenv("EBAY_CLIENT_SECRET", "")
        self.marketplace = marketplace
        self._token = ""
        self._token_expires_at = 0.0

    def available(self):
        return bool(self.client_id and self.secret)

    def _clear_token(self) -> None:
        self._token = ""
        self._token_expires_at = 0.0

    def _access_token(self):
        now = time.monotonic()
        if self._token and now < self._token_expires_at:
            return self._token
        data = post_form_json(
            "https://api.ebay.com/identity/v1/oauth2/token",
            {
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope",
            },
            {"Authorization": basic_auth(self.client_id, self.secret)},
        )
        token = str(data.get("access_token") or "")
        if not token:
            raise RuntimeError("eBay OAuth response did not contain access_token")
        try:
            ttl = float(data.get("expires_in", 7200) or 7200)
        except Exception:
            ttl = 7200.0
        self._token = token
        # Renew before the official expiry so a long-running shadow daemon cannot
        # get stuck on a cached bearer token.
        self._token_expires_at = now + max(1.0, ttl - 60.0)
        return self._token

    def _search(self, query: str, limit: int, token: str):
        url = (
            "https://api.ebay.com/buy/browse/v1/item_summary/search"
            f"?q={quote_plus(query)}&limit={min(limit, 200)}"
        )
        return get_json(
            url,
            {
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": self.marketplace,
            },
        )

    def fetch(self, query: str, limit: int = 50):
        token = self._access_token()
        try:
            data = self._search(query, limit, token)
        except HTTPError as exc:
            if exc.code != 401:
                raise
            self._clear_token()
            data = self._search(query, limit, self._access_token())

        out = []
        for x in data.get("itemSummaries", []):
            price = x.get("price") or {}
            out.append(
                RawListing(
                    source=self.name,
                    external_id=str(x.get("itemId", "")),
                    title=x.get("title", ""),
                    price=float(price.get("value", 0) or 0),
                    currency=price.get("currency", ""),
                    url=x.get("itemWebUrl", ""),
                    condition=x.get("condition", ""),
                    seller=(x.get("seller") or {}).get("username", ""),
                    category=((x.get("categories") or [{}])[0]).get(
                        "categoryName", ""
                    ),
                    extra=x,
                )
            )
        return out
