from __future__ import annotations

import json
from pathlib import Path

from .bricklink import BrickLinkPriceGuideFeed
from .cardmarket_public import CardmarketPublicReferenceFeed
from .discogs import DiscogsReferenceFeed
from .ebay import EbayBrowseFeed
from .etsy import EtsyFeed
from .mercadolibre import MercadoLibreFeed
from .pricecharting import PriceChartingFeed
from .rakuten import RakutenIchibaFeed
from .reverb import ReverbFeed
from .ricardo import RicardoSearchFeed
from .stockx import StockXMarketFeed
from .tcgapi import TCGReferenceFeed


def default_registry_path():
    root = Path(__file__).resolve().parents[3] / "config"
    plain = root / "feeds.json"
    return plain if plain.exists() else root / "feeds.json.z64"


def load_source_registry(path=None):
    p = Path(path) if path else default_registry_path()
    if p.name.endswith(".z64"):
        import base64
        import zlib

        raw = json.loads(
            zlib.decompress(base64.b64decode(p.read_text().strip())).decode("utf-8")
        )
    else:
        raw = json.loads(p.read_text())
    return raw["sources"]


def official_adapters():
    """Authorized adapters that return concrete market/retail listings.

    Reference-price APIs deliberately live in ``reference_adapters`` so a guide
    price or marketplace statistic cannot accidentally become a buy/exit route.
    This function also intentionally excludes scraper adapters for marketplaces
    whose current terms prohibit automated extraction without permission.
    """
    adapters = {
        "ebay": EbayBrowseFeed(),
        "stockx": StockXMarketFeed(),
        "reverb": ReverbFeed(),
        "etsy": EtsyFeed(),
        "rakuten_ichiba": RakutenIchibaFeed(),
        "ricardo": RicardoSearchFeed(),
        "pricecharting": PriceChartingFeed(include_reference_fallback=False),
    }
    for site, suffix in (
        ("MLM", "mx"),
        ("MLA", "ar"),
        ("MLB", "br"),
        ("MLC", "cl"),
        ("MCO", "co"),
        ("MLU", "uy"),
    ):
        name = f"mercadolibre_{suffix}"
        adapters[name] = MercadoLibreFeed(site_id=site, source_name=name)
    return adapters


def reference_adapters():
    """Authorized/public valuation feeds, never executable routes."""
    return {
        # Cardmarket explicitly publishes these catalogue/price-guide downloads
        # for all users; no account/API credential is required.
        "cardmarket_public_reference": CardmarketPublicReferenceFeed(),
        "bricklink_reference": BrickLinkPriceGuideFeed(),
        "discogs_reference": DiscogsReferenceFeed(),
        "tcgapi_reference": TCGReferenceFeed(),
        "pricecharting_reference": PriceChartingFeed(
            include_marketplace_offers=False,
            include_reference_fallback=True,
        ),
    }
