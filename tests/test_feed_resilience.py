import json
from urllib.error import HTTPError

from roman_arb.feeds import ebay, http_utils, mercadolibre


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_http_retries_transient_503(monkeypatch):
    calls = {"n": 0}

    def fake_open(req, timeout=20):
        calls["n"] += 1
        if calls["n"] == 1:
            raise HTTPError(req.full_url, 503, "temporary", {}, None)
        return _Response({"ok": True})

    monkeypatch.setattr(http_utils, "urlopen", fake_open)
    monkeypatch.setattr(http_utils.time, "sleep", lambda _: None)
    assert http_utils.get_json("https://example.test", retries=1) == {"ok": True}
    assert calls["n"] == 2


def test_ebay_refreshes_expired_token(monkeypatch):
    tokens = iter(
        [
            {"access_token": "first", "expires_in": 120},
            {"access_token": "second", "expires_in": 120},
        ]
    )
    monkeypatch.setattr(ebay, "post_form_json", lambda *a, **k: next(tokens))
    f = ebay.EbayBrowseFeed()
    f.client_id = "id"
    f.secret = "secret"
    assert f._access_token() == "first"
    f._token_expires_at = 0.0
    assert f._access_token() == "second"


def test_ebay_reauthenticates_once_after_401(monkeypatch):
    tokens = iter(
        [
            {"access_token": "first", "expires_in": 120},
            {"access_token": "second", "expires_in": 120},
        ]
    )
    monkeypatch.setattr(ebay, "post_form_json", lambda *a, **k: next(tokens))
    calls = {"n": 0}

    def fake_search(self, query, limit, token):
        calls["n"] += 1
        if calls["n"] == 1:
            raise HTTPError("https://example.test", 401, "expired", {}, None)
        assert token == "second"
        return {"itemSummaries": []}

    monkeypatch.setattr(ebay.EbayBrowseFeed, "_search", fake_search)
    f = ebay.EbayBrowseFeed()
    f.client_id = "id"
    f.secret = "secret"
    assert f.fetch("lego") == []
    assert calls["n"] == 2


def test_mercadolibre_is_credential_gated(monkeypatch):
    monkeypatch.delenv("MELI_ACCESS_TOKEN", raising=False)
    assert not mercadolibre.MercadoLibreFeed().available()
    monkeypatch.setenv("MELI_ACCESS_TOKEN", "token")
    assert mercadolibre.MercadoLibreFeed().available()
