from __future__ import annotations

import re
import threading
import time

from .base import RawListing
from .http_utils import get_json


_GAMES = {
    "magic": 1,
    "mtg": 1,
    "pokemon": 6,
    "pokémon": 6,
    "yugioh": 3,
    "yu-gi-oh": 3,
    "one piece": 18,
    "onepiece": 18,
    "lorcana": 19,
    "flesh and blood": 13,
    "fab": 13,
    "digimon": 7,
    "dragon ball super": 9,
    "star wars unlimited": 15,
    "final fantasy": 17,
    "weiss schwarz": 11,
    "weiß schwarz": 11,
}

_BASE = "https://downloads.s3.cardmarket.com/productCatalog"


def _norm(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").lower()))


def _find_rows(obj, preferred_key_fragments: tuple[str, ...]) -> list[dict]:
    """Locate a row-array across Cardmarket download schema revisions."""
    if isinstance(obj, list):
        rows = [x for x in obj if isinstance(x, dict)]
        return rows
    if not isinstance(obj, dict):
        return []
    for key, value in obj.items():
        low = str(key).lower()
        if any(fragment in low for fragment in preferred_key_fragments):
            rows = _find_rows(value, preferred_key_fragments)
            if rows:
                return rows
    for value in obj.values():
        rows = _find_rows(value, preferred_key_fragments)
        if rows:
            return rows
    return []


def _pick(row: dict, *aliases, default=None):
    lower = {str(k).lower().replace("_", "").replace("-", ""): v for k, v in row.items()}
    for alias in aliases:
        key = str(alias).lower().replace("_", "").replace("-", "")
        if key in lower:
            return lower[key]
    return default


def _number(row: dict, *aliases) -> float | None:
    value = _pick(row, *aliases)
    try:
        x = float(value)
        return x if x > 0 else None
    except Exception:
        return None


class CardmarketPublicReferenceFeed:
    """Official public Cardmarket catalogue + daily price-guide downloads.

    Cardmarket made these files publicly downloadable for all users. ROMAN uses
    them as valuation-only evidence. No API token, login automation or page
    scraping is involved, and these rows can never become execution routes.
    """

    name = "cardmarket_public_reference"

    def __init__(self, cache_seconds: float = 6 * 3600):
        self.cache_seconds = max(float(cache_seconds), 300.0)
        self._lock = threading.Lock()
        self._cache: dict[int, tuple[float, list[dict], dict[str, dict]]] = {}

    def available(self):
        return True

    @staticmethod
    def _game_id(query: str) -> int:
        low = (query or "").lower()
        for token, game_id in _GAMES.items():
            if token in low:
                return game_id
        # ROMAN's TCG seed universe is Pokémon-heavy; use Pokémon only when the
        # query itself does not name another game but contains familiar TCG terms.
        if any(token in low for token in ("booster", "charizard", "pikachu", "151")):
            return 6
        return 6

    def _load(self, game_id: int) -> tuple[list[dict], dict[str, dict]]:
        now = time.monotonic()
        cached = self._cache.get(game_id)
        if cached and now - cached[0] < self.cache_seconds:
            return cached[1], cached[2]
        with self._lock:
            cached = self._cache.get(game_id)
            if cached and now - cached[0] < self.cache_seconds:
                return cached[1], cached[2]

            catalogs: list[dict] = []
            for kind in ("singles", "nonsingles"):
                url = f"{_BASE}/productList/products_{kind}_{game_id}.json"
                try:
                    data = get_json(url, retries=1)
                except Exception:
                    continue
                catalogs.extend(_find_rows(data, ("product", "catalog", "data")))

            price_url = f"{_BASE}/priceGuide/price_guide_{game_id}.json"
            price_data = get_json(price_url, retries=1)
            price_rows = _find_rows(price_data, ("price", "guide", "data"))
            prices: dict[str, dict] = {}
            for row in price_rows:
                pid = str(_pick(row, "idProduct", "id_product", "productId", default="") or "")
                if pid:
                    prices[pid] = row
            self._cache[game_id] = (now, catalogs, prices)
            return catalogs, prices

    def fetch(self, query: str, limit: int = 50):
        game_id = self._game_id(query)
        catalog, prices = self._load(game_id)
        q_tokens = set(_norm(query).split())
        if not q_tokens:
            return []

        ranked: list[tuple[float, dict]] = []
        for product in catalog:
            name = str(_pick(product, "name", "productName", "Name", default="") or "")
            expansion = str(_pick(product, "expansionName", "expansion", default="") or "")
            hay = set(_norm(f"{name} {expansion}").split())
            if not hay:
                continue
            overlap = len(q_tokens & hay) / max(len(q_tokens), 1)
            if overlap < 0.45:
                continue
            ranked.append((overlap, product))
        ranked.sort(key=lambda x: x[0], reverse=True)

        out: list[RawListing] = []
        for match_score, product in ranked[: min(limit, 12)]:
            pid = str(_pick(product, "idProduct", "id_product", "id", default="") or "")
            if not pid:
                continue
            price_row = prices.get(pid, {})
            price = (
                _number(price_row, "LOW", "Low Price", "low")
                or _number(price_row, "TREND", "Trend Price", "trend")
                or _number(price_row, "AVG30", "avg30")
                or _number(price_row, "SELL", "Avg. Sell Price", "avg")
            )
            if price is None:
                continue
            name = str(_pick(product, "name", "productName", "Name", default=query) or query)
            expansion = str(_pick(product, "expansionName", "expansion", default="") or "")
            category = str(_pick(product, "categoryName", "category", default="TCG") or "TCG")
            out.append(
                RawListing(
                    source=self.name,
                    external_id=f"price:{game_id}:{pid}",
                    title=f"{name} {expansion}".strip(),
                    price=price,
                    currency="EUR",
                    url="https://www.cardmarket.com/",
                    condition="Cardmarket public price guide",
                    category=category,
                    product_key=f"cardmarket:{pid}",
                    extra={
                        "query": query,
                        "game_id": game_id,
                        "cardmarket_product_id": pid,
                        "reference_only": True,
                        "reference_kind": "official_public_price_guide",
                        "executable_confidence": 0.10,
                        "catalog_match": match_score,
                        "price_guide": price_row,
                        "catalog_product": product,
                    },
                )
            )
            if len(out) >= limit:
                break
        return out
