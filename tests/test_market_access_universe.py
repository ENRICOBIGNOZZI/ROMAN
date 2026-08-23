from roman_arb.feeds import (
    market_access_registry,
    official_adapters,
    reference_adapters,
)
from roman_arb.feeds.cardmarket_public import CardmarketPublicReferenceFeed
from roman_arb.feeds.ebay import EbayBrowseFeed
from roman_arb.feeds.pricecharting import PriceChartingFeed
from roman_arb.feeds.ricardo import RicardoSearchFeed


def test_named_no_scrape_markets_remain_disabled_for_automated_collection():
    policies = market_access_registry()
    for source in (
        "vinted",
        "tutti",
        "subito",
        "wallapop",
        "kleinanzeigen",
        "leboncoin",
    ):
        assert source in policies
        assert not policies[source].automated_collection
        assert policies[source].access_mode == "permission_required"


def test_public_cardmarket_download_is_credential_free_and_reference_only():
    policy = market_access_registry()["cardmarket_public"]
    assert policy.automated_collection
    assert policy.access_mode == "public_official_download"
    assert policy.credential_env == ()
    assert CardmarketPublicReferenceFeed().available()


def test_market_and_reference_adapter_registries_are_separate(monkeypatch):
    for key in (
        "RICARDO_TOKEN",
        "PRICECHARTING_TOKEN",
        "BRICKLINK_CONSUMER_KEY",
        "BRICKLINK_CONSUMER_SECRET",
        "BRICKLINK_TOKEN",
        "BRICKLINK_TOKEN_SECRET",
        "DISCOGS_TOKEN",
        "TCGAPI_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    market = official_adapters()
    refs = reference_adapters()

    assert isinstance(market["ricardo"], RicardoSearchFeed)
    assert isinstance(market["pricecharting"], PriceChartingFeed)
    assert "cardmarket_public_reference" not in market
    assert "bricklink_reference" not in market
    assert "discogs_reference" not in market

    assert isinstance(refs["cardmarket_public_reference"], CardmarketPublicReferenceFeed)
    assert refs["cardmarket_public_reference"].available()
    assert not refs["bricklink_reference"].available()
    assert not refs["discogs_reference"].available()

    for source in (
        "vinted",
        "tutti",
        "subito",
        "wallapop",
        "kleinanzeigen",
        "leboncoin",
    ):
        assert source not in market
        assert source not in refs


def test_pricecharting_market_offer_uses_upc_global_identity(monkeypatch):
    feed = PriceChartingFeed(token="token", include_marketplace_offers=True)

    def fake_call(path, **params):
        if path == "/api/products":
            return {"products": [{"id": "123", "product-name": "EarthBound"}]}
        if path == "/api/product":
            return {
                "id": "123",
                "product-name": "EarthBound",
                "console-name": "Super Nintendo",
                "upc": "045496830434",
                "genre": "RPG",
            }
        if path == "/api/offers":
            return {
                "offers": [
                    {
                        "offer-id": "o1",
                        "product-name": "EarthBound",
                        "console-name": "Super Nintendo",
                        "price": 25000,
                        "offer-url": "/offer/o1",
                    }
                ]
            }
        raise AssertionError(path)

    monkeypatch.setattr(feed, "_call", fake_call)
    rows = feed.fetch("EarthBound Super Nintendo")
    assert len(rows) == 1
    row = rows[0]
    assert row.source == "pricecharting"
    assert row.price == 250.0
    assert row.product_key == "gtin:045496830434"
    assert row.extra["global_product_key"] == "gtin:045496830434"
    assert not row.extra["reference_only"]


def test_ebay_prefers_gtin_then_epid_for_global_identity():
    assert EbayBrowseFeed._global_key({"gtin": "123"}) == "gtin:123"
    assert EbayBrowseFeed._global_key({"epid": "456"}) == "epid:456"
    assert EbayBrowseFeed._global_key({"gtin": "123", "epid": "456"}) == "gtin:123"


def test_cardmarket_public_reference_parses_cached_catalog_without_network(monkeypatch):
    feed = CardmarketPublicReferenceFeed()
    catalog = [
        {
            "idProduct": 42,
            "name": "Scarlet & Violet 151 Booster Bundle",
            "categoryName": "Booster",
            "expansionName": "151",
        }
    ]
    prices = {
        "42": {
            "idProduct": 42,
            "LOW": 32.5,
            "TREND": 35.1,
            "AVG30": 34.8,
        }
    }
    monkeypatch.setattr(feed, "_load", lambda game_id: (catalog, prices))
    rows = feed.fetch("Pokemon 151 booster bundle")
    assert len(rows) == 1
    assert rows[0].source == "cardmarket_public_reference"
    assert rows[0].price == 32.5
    assert rows[0].currency == "EUR"
    assert rows[0].extra["reference_only"] is True
