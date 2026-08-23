from __future__ import annotations

import math
import os

from .base import RawListing
from .http_utils import post_json


class RicardoSearchFeed:
    """Ricardo official partner API search adapter.

    The live service requires a Ricardo token credential issued through the
    partnership/authentication flow.  ROMAN intentionally accepts the resulting
    token through ``RICARDO_TOKEN`` rather than automating end-user login.
    """

    name = "ricardo"
    endpoint = "https://ws.ricardo.ch/ricardoapi/SearchService.Json.svc/SimpleSearch"

    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("RICARDO_TOKEN", "")

    def available(self):
        return bool(self.token)

    @staticmethod
    def _pick(d: dict, *names, default=None):
        lower = {str(k).lower(): v for k, v in d.items()}
        for name in names:
            if str(name).lower() in lower:
                return lower[str(name).lower()]
        return default

    @classmethod
    def _number(cls, value) -> float:
        if isinstance(value, dict):
            value = cls._pick(value, "Amount", "Value", "Price", default=0.0)
        try:
            x = float(value)
            return x if math.isfinite(x) else 0.0
        except Exception:
            return 0.0

    @classmethod
    def _article_rows(cls, obj) -> list[dict]:
        """Locate the article list across Ricardo's versioned response wrappers."""
        candidates: list[list[dict]] = []

        def walk(x):
            if isinstance(x, list):
                rows = [r for r in x if isinstance(r, dict)]
                if rows:
                    candidates.append(rows)
                for r in x:
                    walk(r)
            elif isinstance(x, dict):
                for v in x.values():
                    walk(v)

        walk(obj)
        if not candidates:
            return []
        # Prefer a list that looks like actual marketplace articles.
        def score(rows: list[dict]):
            if not rows:
                return 0
            keys = {str(k).lower() for k in rows[0].keys()}
            return sum(
                int(any(token in key for key in keys))
                for token in ("article", "title", "price", "bid", "buy")
            )

        return max(candidates, key=score)

    def fetch(self, query: str, limit: int = 50):
        if not self.available():
            return []
        payload = {
            "simpleSearchParameter": {
                "AscendingSort": True,
                "CategoryId": 1,
                "CategoryInfos": False,
                "Language": 1,
                "PageNumber": 1,
                "PageSize": min(max(int(limit), 1), 50),
                "SearchText": query,
                "SortBy": 0,
            }
        }
        data = post_json(
            self.endpoint,
            payload,
            {"Ricardo-Username": self.token},
            retries=1,
        )
        rows = self._article_rows(data)
        out: list[RawListing] = []
        for row in rows[:limit]:
            article_id = str(
                self._pick(row, "ArticleId", "Id", "ArticleID", default="") or ""
            )
            title = str(
                self._pick(row, "Title", "ArticleTitle", "Name", default=query) or query
            )
            price = 0.0
            for key in (
                "BuyNowPrice",
                "FixedPrice",
                "CurrentPrice",
                "CurrentBidPrice",
                "StartPrice",
                "Price",
            ):
                price = self._number(self._pick(row, key, default=0.0))
                if price > 0:
                    break
            if price <= 0:
                continue
            currency = str(
                self._pick(row, "Currency", "CurrencyCode", default="CHF") or "CHF"
            )
            url = str(
                self._pick(row, "Url", "ArticleUrl", "WebUrl", default="") or ""
            )
            seller = self._pick(
                row, "SellerNickname", "SellerName", "SellerUserName", default=""
            )
            out.append(
                RawListing(
                    source=self.name,
                    external_id=article_id or f"search:{len(out)}:{title[:32]}",
                    title=title,
                    price=price,
                    currency=currency,
                    url=url,
                    condition=str(
                        self._pick(row, "Condition", "ArticleCondition", default="") or ""
                    ),
                    seller=str(seller or ""),
                    category=str(
                        self._pick(row, "CategoryName", "Category", default="") or ""
                    ),
                    product_key=str(
                        self._pick(row, "ProductId", "InternalReference", default="") or ""
                    ),
                    extra={
                        "query": query,
                        "reference_only": False,
                        "executable_confidence": 0.42,
                        "ricardo_article": row,
                    },
                )
            )
        return out
