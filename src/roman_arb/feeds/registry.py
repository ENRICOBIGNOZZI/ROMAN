from __future__ import annotations

import json
from pathlib import Path

from .bricklink import BrickLinkPriceGuideFeed
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
    """Authorized/contracted adapters only.

    This function intentionally does not create scraper adapters for marketplaces
    whose current terms prohibit automated extraction. Those markets remain in
    the access-policy registry until explicit permission/partner access exists.
    """
    adapters = {
        "ebay": EbayBrowseFeed(),
        "stockx": StockXMarketFeed(),
        "reverb": ReverbFeed(),
        "etsy": EtsyFeed(),
        "rakuten_ichiba": RakutenIchibaFeed(),
        "ricardo": RicardoSearchFeed(),
        "pricecharting": PriceChartingFeed(),
        "bricklink": BrickLinkPriceGuideFeed(),
        "discogs": DiscogsReferenceFeed(),
        "tcgapi": TCGReferenceFeed(),
    }
    # Mercado Libre site adapters are read-only but credential-gated. Without an
    # authorized MELI_ACCESS_TOKEN they remain NO_CREDENTIALS/PRE-SHADOW rather
    # than repeatedly treating auth failures as market-data observations.
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
