from __future__ import annotations
import json
from pathlib import Path
from .ebay import EbayBrowseFeed
from .stockx import StockXMarketFeed
from .reverb import ReverbFeed
from .etsy import EtsyFeed
from .mercadolibre import MercadoLibreFeed
from .rakuten import RakutenIchibaFeed


def default_registry_path():
    root = Path(__file__).resolve().parents[3] / "config"
    plain = root / "feeds.json"
    return plain if plain.exists() else root / "feeds.json.z64"


def load_source_registry(path=None):
    p = Path(path) if path else default_registry_path()
    if p.name.endswith(".z64"):
        import base64, zlib
        raw = json.loads(zlib.decompress(base64.b64decode(p.read_text().strip())).decode("utf-8"))
    else:
        raw = json.loads(p.read_text())
    return raw["sources"]


def official_adapters():
    adapters = {
        "ebay": EbayBrowseFeed(),
        "stockx": StockXMarketFeed(),
        "reverb": ReverbFeed(),
        "etsy": EtsyFeed(),
        "rakuten_ichiba": RakutenIchibaFeed(),
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
