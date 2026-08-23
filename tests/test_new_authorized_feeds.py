import pytest

import roman_arb.feeds.keepa as keepa_module
from roman_arb.feeds.cardtrader import CardTraderMarketFeed
from roman_arb.feeds.keepa import KeepaReferenceFeed
from roman_arb.feeds.watchcharts import WatchChartsReferenceFeed


def test_watchcharts_parses_brand_reference_and_returns_reference_rows(monkeypatch):
    feed = WatchChartsReferenceFeed(api_key="key")

    def fake_get(path, **params):
        if path == "/search/watch":
            assert params["brand_name"] == "rolex"
            assert params["reference"] == "124270"
            return {"results": [{"uuid": "u1", "model": "124270"}]}
        if path == "/watch/info":
            return {
                "brand": "Rolex",
                "collection": "Explorer",
                "model": "124270",
                "market_price": 6500,
                "dealer_price": 6900,
                "median_asking_price": 6700,
                "volatility": 0.05,
            }
        raise AssertionError(path)

    monkeypatch.setattr(feed, "_get", fake_get)
    rows = feed.fetch("Rolex 124270")
    assert rows
    assert all(row.source == "watchcharts_reference" for row in rows)
    assert all(row.extra["reference_only"] is True for row in rows)
    assert rows[0].price == pytest.approx(6500.0)


def test_keepa_reference_uses_current_price_statistics(monkeypatch):
    feed = KeepaReferenceFeed(api_key="key", domain_id=3, max_products=1)

    def fake_get_json(url, headers=None, retries=0):
        assert "type=product" in url
        assert "domain=3" in url
        return {
            "products": [
                {
                    "asin": "B012345678",
                    "title": "Nintendo Switch OLED",
                    "websiteDisplayGroupName": "Video Games",
                    "stats": {"current": [-1, 29999, 24999]},
                }
            ]
        }

    monkeypatch.setattr(keepa_module, "get_json", fake_get_json)
    rows = feed.fetch("Nintendo Switch OLED")
    assert len(rows) == 1
    assert rows[0].source == "keepa_reference"
    assert rows[0].price == pytest.approx(299.99)
    assert rows[0].currency == "EUR"
    assert rows[0].extra["reference_kind"] == "keepa_new"
    assert rows[0].extra["reference_only"] is True


def test_cardtrader_marketplace_rows_are_concrete_and_read_only(monkeypatch):
    feed = CardTraderMarketFeed(token="token")
    games = [{"id": 6, "name": "Pokemon"}]
    expansions = [{"id": 151, "game_id": 6, "name": "151", "code": "MEW"}]
    monkeypatch.setattr(feed, "_metadata", lambda: (games, expansions))

    def fake_get(path, **params):
        assert path == "/marketplace/products"
        assert params["expansion_id"] == 151
        return {
            "9001": [
                {
                    "id": 1234,
                    "blueprint_id": 9001,
                    "name_en": "Booster Box",
                    "quantity": 2,
                    "price": {"cents": 8999, "currency": "EUR"},
                    "properties_hash": {"condition": "Near Mint"},
                    "expansion": {"id": 151, "name_en": "151"},
                    "user": {"username": "seller", "country_code": "IT"},
                    "graded": False,
                    "on_vacation": False,
                }
            ]
        }

    monkeypatch.setattr(feed, "_get", fake_get)
    rows = feed.fetch("Pokemon 151 booster box")
    assert len(rows) == 1
    row = rows[0]
    assert row.source == "cardtrader"
    assert row.price == pytest.approx(89.99)
    assert row.extra["reference_only"] is False
    assert row.extra["blueprint_id"] == "9001"


def test_cardtrader_ignores_vacation_products(monkeypatch):
    feed = CardTraderMarketFeed(token="token")
    monkeypatch.setattr(
        feed,
        "_metadata",
        lambda: (
            [{"id": 6, "name": "Pokemon"}],
            [{"id": 151, "game_id": 6, "name": "151", "code": "MEW"}],
        ),
    )
    monkeypatch.setattr(
        feed,
        "_get",
        lambda path, **params: {
            "1": [
                {
                    "id": 1,
                    "blueprint_id": 1,
                    "name_en": "Booster Box",
                    "price": {"cents": 8000, "currency": "EUR"},
                    "expansion": {"name_en": "151"},
                    "user": {"username": "seller"},
                    "on_vacation": True,
                }
            ]
        },
    )
    assert feed.fetch("Pokemon 151 booster box") == []
