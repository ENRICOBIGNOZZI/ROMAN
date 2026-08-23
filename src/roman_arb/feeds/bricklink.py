from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import time
import uuid
from urllib.parse import quote, urlencode, urlsplit

from .base import RawListing
from .http_utils import get_json


def _pct(x: str) -> str:
    return quote(str(x), safe="~-._")


class BrickLinkPriceGuideFeed:
    """BrickLink official API price-guide adapter for LEGO sets.

    BrickLink's public API does not provide a global search endpoint equivalent
    to a marketplace listing search.  ROMAN therefore uses the current stock
    price guide only as conservative ``reference_only`` evidence.  It can improve
    fair-value calibration but can never become an acquisition or exit route.
    """

    name = "bricklink"
    base = "https://api.bricklink.com/api/store/v1"

    def __init__(self):
        self.consumer_key = os.getenv("BRICKLINK_CONSUMER_KEY", "")
        self.consumer_secret = os.getenv("BRICKLINK_CONSUMER_SECRET", "")
        self.token = os.getenv("BRICKLINK_TOKEN", "")
        self.token_secret = os.getenv("BRICKLINK_TOKEN_SECRET", "")

    def available(self):
        return all(
            (
                self.consumer_key,
                self.consumer_secret,
                self.token,
                self.token_secret,
            )
        )

    @staticmethod
    def _set_number(query: str) -> str | None:
        # LEGO catalog set numbers are commonly written as 75192 or 75192-1.
        m = re.search(r"\b(\d{3,6})(?:-(\d+))?\b", query or "")
        if not m:
            return None
        return f"{m.group(1)}-{m.group(2) or '1'}"

    def _auth(self, method: str, url: str, query: dict[str, str]) -> str:
        oauth = {
            "oauth_consumer_key": self.consumer_key,
            "oauth_nonce": uuid.uuid4().hex,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_token": self.token,
            "oauth_version": "1.0",
        }
        params = {**query, **oauth}
        normalized = "&".join(
            f"{_pct(k)}={_pct(v)}" for k, v in sorted(params.items())
        )
        parts = urlsplit(url)
        base_url = f"{parts.scheme}://{parts.netloc}{parts.path}"
        base_string = "&".join((_pct(method.upper()), _pct(base_url), _pct(normalized)))
        key = f"{_pct(self.consumer_secret)}&{_pct(self.token_secret)}"
        sig = base64.b64encode(
            hmac.new(key.encode(), base_string.encode(), hashlib.sha1).digest()
        ).decode()
        oauth["oauth_signature"] = sig
        return "OAuth " + ", ".join(
            f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(oauth.items())
        )

    def _get(self, path: str, **params):
        query = {str(k): str(v) for k, v in params.items() if v is not None}
        base_url = self.base + path
        url = base_url + ("?" + urlencode(query) if query else "")
        return get_json(
            url,
            {"Authorization": self._auth("GET", base_url, query)},
            retries=1,
        )

    def fetch(self, query: str, limit: int = 50):
        if not self.available():
            return []
        set_no = self._set_number(query)
        if not set_no:
            return []
        response = self._get(
            f"/items/SET/{set_no}/price",
            guide_type="stock",
            new_or_used="N",
            region="europe",
            currency_code="EUR",
        )
        data = (response or {}).get("data") or {}
        details = list(data.get("price_detail") or [])
        out: list[RawListing] = []
        for i, x in enumerate(details[:limit]):
            try:
                price = float(x.get("unit_price") or 0.0)
            except Exception:
                price = 0.0
            if price <= 0:
                continue
            out.append(
                RawListing(
                    source=self.name,
                    external_id=f"guide:{set_no}:{i}",
                    title=f"LEGO {set_no} {query}".strip(),
                    price=price,
                    currency=str(data.get("currency_code") or "EUR"),
                    url=f"https://www.bricklink.com/v2/catalog/catalogitem.page?S={set_no}",
                    condition="New",
                    category="LEGO",
                    product_key=f"bricklink:set:{set_no}",
                    extra={
                        "query": query,
                        "reference_only": True,
                        "reference_kind": "bricklink_stock_price_guide",
                        "executable_confidence": 0.16,
                        "shipping_available": x.get("shipping_available"),
                        "price_guide": data,
                    },
                )
            )
        if not out:
            # A summary reference remains useful even when detailed rows are not
            # returned for the caller's region/profile.
            try:
                price = float(data.get("min_price") or data.get("avg_price") or 0.0)
            except Exception:
                price = 0.0
            if price > 0:
                out.append(
                    RawListing(
                        source=self.name,
                        external_id=f"guide:{set_no}:summary",
                        title=f"LEGO {set_no} {query}".strip(),
                        price=price,
                        currency=str(data.get("currency_code") or "EUR"),
                        url=f"https://www.bricklink.com/v2/catalog/catalogitem.page?S={set_no}",
                        condition="New",
                        category="LEGO",
                        product_key=f"bricklink:set:{set_no}",
                        extra={
                            "query": query,
                            "reference_only": True,
                            "reference_kind": "bricklink_stock_summary",
                            "executable_confidence": 0.10,
                            "price_guide": data,
                        },
                    )
                )
        return out
