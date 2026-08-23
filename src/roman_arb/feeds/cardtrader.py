from __future__ import annotations

import os
import re
import threading
import time
from urllib.parse import urlencode

from .base import RawListing
from .http_utils import get_json


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


class CardTraderMarketFeed:
    """Official CardTrader marketplace listing adapter.

    CardTrader exposes marketplace products purchasable through its documented
    cart API. ROMAN only reads available products; it does not submit purchases.
    Queries are resolved to an expansion and the marketplace endpoint is then
    filtered locally for the best matching products.
    """

    name = "cardtrader"
    base = "https://api.cardtrader.com/api/v2"

    def __init__(self, token: str | None = None, cache_seconds: float = 6 * 3600):
        self.token = token or os.getenv("CARDTRADER_TOKEN", "")
        self.cache_seconds = max(float(cache_seconds), 300.0)
        self._lock = threading.Lock()
        self._cache_at = 0.0
        self._games: list[dict] = []
        self._expansions: list[dict] = []

    def available(self):
        return bool(self.token)

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    def _get(self, path: str, **params):
        url = self.base + path
        if params:
            url += "?" + urlencode(params)
        return get_json(url, self._headers(), retries=1)

    def _metadata(self) -> tuple[list[dict], list[dict]]:
        now = time.monotonic()
        if self._games and self._expansions and now - self._cache_at < self.cache_seconds:
            return self._games, self._expansions
        with self._lock:
            if self._games and self._expansions and now - self._cache_at < self.cache_seconds:
                return self._games, self._expansions
            self._games = list(self._get("/games") or [])
            self._expansions = list(self._get("/expansions") or [])
            self._cache_at = time.monotonic()
            return self._games, self._expansions

    @staticmethod
    def _game_hint(query: str, games: list[dict]) -> int | None:
        q = (query or "").lower()
        aliases = {
            "pokemon": ("pokemon", "pokémon"),
            "magic": ("magic", "mtg"),
            "one piece": ("one piece",),
            "lorcana": ("lorcana",),
            "yugioh": ("yugioh", "yu-gi-oh"),
        }
        wanted = ""
        for canonical, values in aliases.items():
            if any(value in q for value in values):
                wanted = canonical
                break
        if not wanted:
            return None
        for game in games:
            name = str(game.get("name") or "").lower()
            if wanted in name or name in wanted:
                try:
                    return int(game.get("id"))
                except Exception:
                    return None
        return None

    @classmethod
    def _best_expansion(cls, query: str, games: list[dict], expansions: list[dict]):
        q_tokens = _tokens(query)
        game_id = cls._game_hint(query, games)
        ranked = []
        for expansion in expansions:
            try:
                eid = int(expansion.get("id"))
            except Exception:
                continue
            if game_id is not None:
                try:
                    if int(expansion.get("game_id")) != game_id:
                        continue
                except Exception:
                    continue
            name = str(expansion.get("name") or "")
            code = str(expansion.get("code") or "")
            tokens = _tokens(f"{name} {code}")
            if not tokens:
                continue
            overlap = len(q_tokens & tokens) / max(len(tokens), 1)
            containment = 1.0 if name.lower() and name.lower() in (query or "").lower() else 0.0
            score = 0.7 * overlap + 0.3 * containment
            if score > 0:
                ranked.append((score, eid, expansion))
        if not ranked:
            return None
        ranked.sort(reverse=True, key=lambda x: x[0])
        return ranked[0]

    @staticmethod
    def _flatten_products(data) -> list[dict]:
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if not isinstance(data, dict):
            return []
        out = []
        for value in data.values():
            if isinstance(value, list):
                out.extend(x for x in value if isinstance(x, dict))
        return out

    def fetch(self, query: str, limit: int = 50):
        if not self.available():
            return []
        games, expansions = self._metadata()
        best = self._best_expansion(query, games, expansions)
        if best is None:
            return []
        expansion_score, expansion_id, expansion = best
        data = self._get("/marketplace/products", expansion_id=expansion_id)
        products = self._flatten_products(data)
        q_tokens = _tokens(query)
        ranked = []
        for product in products:
            name = str(product.get("name_en") or "")
            expansion_name = str((product.get("expansion") or {}).get("name_en") or expansion.get("name") or "")
            p_tokens = _tokens(f"{name} {expansion_name}")
            overlap = len(q_tokens & p_tokens) / max(len(q_tokens), 1)
            if overlap < 0.35:
                continue
            if bool(product.get("on_vacation")):
                continue
            ranked.append((overlap, product))
        ranked.sort(reverse=True, key=lambda x: x[0])

        out: list[RawListing] = []
        for overlap, product in ranked[:limit]:
            price_obj = product.get("price") or {}
            try:
                cents = int(price_obj.get("cents") or 0)
            except Exception:
                cents = 0
            if cents <= 0:
                continue
            currency = str(price_obj.get("currency") or "EUR")
            user = product.get("user") or {}
            expansion_obj = product.get("expansion") or {}
            blueprint_id = str(product.get("blueprint_id") or "")
            properties = product.get("properties_hash") or {}
            condition = str(properties.get("condition") or "")
            name = str(product.get("name_en") or query)
            expansion_name = str(expansion_obj.get("name_en") or expansion.get("name") or "")
            out.append(
                RawListing(
                    source=self.name,
                    external_id=str(product.get("id") or f"ct:{len(out)}"),
                    title=f"{name} {expansion_name}".strip(),
                    price=cents / 100.0,
                    currency=currency,
                    url="https://www.cardtrader.com/",
                    condition=condition,
                    seller=str(user.get("username") or ""),
                    category="TCG marketplace",
                    product_key=(f"cardtrader:{blueprint_id}" if blueprint_id else ""),
                    extra={
                        "query": query,
                        "reference_only": False,
                        "executable_confidence": 0.62,
                        "expansion_match": expansion_score,
                        "product_match": overlap,
                        "blueprint_id": blueprint_id,
                        "quantity": product.get("quantity"),
                        "bundle_size": product.get("bundle_size"),
                        "graded": product.get("graded"),
                        "seller_country": user.get("country_code"),
                        "can_sell_via_hub": user.get("can_sell_via_hub"),
                        "cardtrader_product": product,
                    },
                )
            )
        return out
