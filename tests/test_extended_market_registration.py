from roman_arb.feeds import market_access_registry, official_adapters, reference_adapters
from roman_arb.production import ShadowLiveEngine


def _engine(tmp_path):
    return ShadowLiveEngine(
        capital=10_000,
        snapshot_db=str(tmp_path / "market.sqlite"),
        reference_snapshot_db=str(tmp_path / "reference.sqlite"),
        tracking_db=str(tmp_path / "tracking.sqlite"),
        shadow_db=str(tmp_path / "shadow.sqlite"),
        dashboard_path=str(tmp_path / "dashboard.json"),
    )


def test_extended_authorized_sources_are_registered(monkeypatch):
    for key in (
        "CARDTRADER_TOKEN",
        "WATCHCHARTS_API_KEY",
        "KEEPA_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    market = official_adapters()
    refs = reference_adapters()
    policies = market_access_registry()

    assert "cardtrader" in market
    assert "watchcharts_reference" in refs
    assert "keepa_reference" in refs
    assert policies["cardtrader"].automated_collection
    assert policies["watchcharts"].automated_collection
    assert policies["keepa"].automated_collection
    assert not market["cardtrader"].available()
    assert not refs["watchcharts_reference"].available()
    assert not refs["keepa_reference"].available()


def test_production_plans_activate_specialized_sources(tmp_path):
    engine = _engine(tmp_path)
    try:
        assert "cardtrader" in engine.plan
        assert "pricecharting" in engine.plan
        assert "ricardo" in engine.plan
        assert any("Pokemon 151" in q for q in engine.plan["cardtrader"])
        assert "watchcharts_reference" in engine.reference_adapters
        assert "keepa_reference" in engine.reference_adapters
    finally:
        engine.close()
