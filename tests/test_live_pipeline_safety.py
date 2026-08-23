from datetime import datetime, timezone

from roman_arb.fx import FXBook
from roman_arb.live import ShadowLiveEngine
import roman_arb.live as live_module


def _engine(tmp_path):
    return ShadowLiveEngine(
        capital=10_000,
        snapshot_db=str(tmp_path / "snap.sqlite"),
        tracking_db=str(tmp_path / "track.sqlite"),
        shadow_db=str(tmp_path / "shadow.sqlite"),
        dashboard_path=str(tmp_path / "dashboard.json"),
    )


def test_return_model_uses_same_source_prices_not_cross_market_composition(tmp_path):
    e = _engine(tmp_path)
    try:
        key = "id:lego:75192"
        first = {
            key: [
                {"source": "a", "price_eur": 100.0, "title": "LEGO 75192", "extra": {"query": "LEGO 75192"}},
                {"source": "b", "price_eur": 140.0, "title": "LEGO 75192", "extra": {"query": "LEGO 75192"}},
            ]
        }
        e._update_return_models(first)
        second = {
            key: [
                {"source": "a", "price_eur": 100.0, "title": "LEGO 75192", "extra": {"query": "LEGO 75192"}},
            ]
        }
        e._update_return_models(second)
        assert key in e._latest_entity_return
        assert abs(e._latest_entity_return[key]) < 1e-12
    finally:
        e.close()


def test_dashboard_regime_status_depends_on_regime_not_kalman(tmp_path):
    e = _engine(tmp_path)
    try:
        e.model.regime.update("lego_sealed", 0.001)
        e.model.regime.update("lego_sealed", 0.002)
        payload = e.dashboard_payload([], [])
        assert payload["model_status"]["Regime detector"] == "ONLINE"
        assert payload["model_status"]["Dynamic Kalman factors"] == "WARMUP"
        assert payload["model_status"]["Text + image condition risk"] == "TEXT_ONLY"
    finally:
        e.close()


def test_live_comparable_exit_pays_fx_friction_and_condition_text_is_used(tmp_path, monkeypatch):
    e = _engine(tmp_path)
    try:
        now = datetime.now(timezone.utc).isoformat()
        fx = FXBook(
            {"EUR": 1.0, "USD": 1.20},
            asof=now,
            friction_pct=0.01,
        )
        e.refresh_fx = lambda: fx
        rows = [
            {
                "source": "ebay",
                "external_id": "buy",
                "title": "LEGO Star Wars Millennium Falcon 75192",
                "price": 100.0,
                "currency": "EUR",
                "condition": "damaged cracked untested as-is",
                "seller": "seller-a",
                "category": "",
                "product_key": "",
                "url": "",
                "observed_at": now,
                "extra": {"query": "LEGO 75192"},
            },
            {
                "source": "stockx",
                "external_id": "exit",
                "title": "LEGO 75192 Millennium Falcon",
                "price": 144.0,
                "currency": "USD",
                "condition": "new",
                "seller": "",
                "category": "",
                "product_key": "",
                "url": "",
                "observed_at": now,
                "extra": {"query": "LEGO 75192"},
            },
        ]
        monkeypatch.setattr(live_module, "_latest_rows", lambda *a, **k: rows)
        candidates = e.build_candidates()
        c = next(x for x in candidates if x["buy_source"] == "ebay")
        comp = next(x for x in c["comparables_net"] if x["source"] == "stockx")
        venue = e.venues["stockx"]
        gross_mid_eur = 144.0 / 1.20
        gross_mark = gross_mid_eur * (1.0 - float(venue.price_haircut)) * 0.95
        no_fx_friction = gross_mark * (1.0 - float(venue.sell_fee)) - float(venue.fixed_exit)
        assert comp["net_value"] < no_fx_friction
        assert c["description"] == "damaged cracked untested as-is"
        assert c["condition_risk"] > 0.2
    finally:
        e.close()
