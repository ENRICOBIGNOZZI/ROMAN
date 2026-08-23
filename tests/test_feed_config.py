from roman_arb.feeds.ebay import EbayBrowseFeed
from roman_arb.feeds.registry import official_adapters


def test_ebay_marketplace_can_be_set_by_environment(monkeypatch):
    monkeypatch.setenv("EBAY_MARKETPLACE_ID", "EBAY_DE")
    assert EbayBrowseFeed().marketplace == "EBAY_DE"


def test_ebay_explicit_marketplace_overrides_environment(monkeypatch):
    monkeypatch.setenv("EBAY_MARKETPLACE_ID", "EBAY_DE")
    assert EbayBrowseFeed(marketplace="EBAY_IT").marketplace == "EBAY_IT"


def test_mercadolibre_registry_is_credential_gated(monkeypatch):
    monkeypatch.delenv("MELI_ACCESS_TOKEN", raising=False)
    adapters = official_adapters()
    meli = [v for k, v in adapters.items() if k.startswith("mercadolibre_")]
    assert len(meli) >= 1
    assert all(not x.available() for x in meli)
