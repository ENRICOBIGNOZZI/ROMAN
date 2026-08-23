import pytest

from roman_arb.production import ShadowLiveEngine


def _engine(tmp_path):
    return ShadowLiveEngine(
        capital=10_000,
        snapshot_db=str(tmp_path / "snap.sqlite"),
        tracking_db=str(tmp_path / "track.sqlite"),
        shadow_db=str(tmp_path / "shadow.sqlite"),
        dashboard_path=str(tmp_path / "dashboard.json"),
    )


def test_closed_executable_outcome_updates_value_and_hazard_only(tmp_path):
    engine = _engine(tmp_path)
    try:
        engine._last_scored_candidates = [
            {
                "entity_key": "id:cards:x",
                "sector": "cards",
                "family": "graded",
                "seller_route_key": "seller-a:buy->exit",
                "exit_source": "ebay",
                "locked": True,
                "locked_exit_bid": 120.0,
                "exit_fee_rate": 0.10,
                "exit_fixed": 0.0,
                "exit_shipping": 0.0,
                "authentication_cost": 0.0,
                "fx_cost": 0.0,
                "repair_cost": 0.0,
                "expected_return_loss": 0.0,
                "expected_fraud_loss": 0.0,
                "exit_tax": 0.0,
            }
        ]
        learned = engine._learn_closed_outcomes(
            [
                {
                    "entity_key": "id:cards:x",
                    "exit_source": "ebay",
                    "close_value": 108.0,
                    "roi": 0.08,
                    "age_days": 5.0,
                }
            ]
        )
        assert learned == 1
        assert engine.model.hierarchy.global_stat.n == 1
        estimate = engine.model.hierarchy.predict(
            "cards", "graded", "id:cards:x"
        )
        assert estimate is not None
        assert estimate.price == pytest.approx(120.0)
        hz = engine.model.hazard.stats["cards|graded"]
        assert hz.sales == 1.0
        assert hz.exposure_days == pytest.approx(5.0)
        # P&L was positive, but seller quality must not be inferred from P&L.
        assert "seller-a:buy->exit" not in engine.model.sellers.stats
    finally:
        engine.close()


def test_closed_feedback_is_bound_to_recorded_exit_source(tmp_path):
    engine = _engine(tmp_path)
    try:
        common = {
            "entity_key": "id:cards:x",
            "sector": "cards",
            "family": "graded",
            "locked": True,
            "exit_fee_rate": 0.10,
        }
        engine._last_scored_candidates = [
            dict(common, exit_source="stockx", locked_exit_bid=150.0),
            dict(common, exit_source="ebay", locked_exit_bid=120.0),
        ]
        learned = engine._learn_closed_outcomes(
            [
                {
                    "entity_key": "id:cards:x",
                    "exit_source": "ebay",
                    "close_value": 108.0,
                    "roi": 0.08,
                    "age_days": 5.0,
                }
            ]
        )
        assert learned == 1
        estimate = engine.model.hierarchy.predict(
            "cards", "graded", "id:cards:x"
        )
        assert estimate is not None
        assert estimate.price == pytest.approx(120.0)
    finally:
        engine.close()


def test_feedback_is_fail_closed_without_exact_executable_route(tmp_path):
    engine = _engine(tmp_path)
    try:
        engine._last_scored_candidates = [
            {
                "entity_key": "id:cards:other",
                "sector": "cards",
                "exit_source": "ebay",
                "locked": True,
                "locked_exit_bid": 120.0,
            }
        ]
        learned = engine._learn_closed_outcomes(
            [
                {
                    "entity_key": "id:cards:x",
                    "exit_source": "ebay",
                    "close_value": 108.0,
                    "roi": 0.08,
                    "age_days": 5.0,
                }
            ]
        )
        assert learned == 0
        assert engine.model.hierarchy.global_stat.n == 0
    finally:
        engine.close()


def test_production_dashboard_names_unified_decision_rule(tmp_path):
    engine = _engine(tmp_path)
    try:
        payload = engine.dashboard_payload([], [])
        assert "Conservative ensemble" not in payload["model_status"]
        assert payload["model_status"]["Unified predictive LCB"] == "ONLINE"
    finally:
        engine.close()


def test_dashboard_separates_expected_roi_from_lcb(tmp_path):
    engine = _engine(tmp_path)
    try:
        candidate = {
            "entity_key": "id:x",
            "title": "x",
            "acquisition_cost": 100.0,
            "expected_exit_net": 120.0,
            "conservative_net_roi": 0.05,
            "lcb_net_roi": 0.05,
            "expected_holding_days": 10.0,
            "score_per_capital_day": 0.005,
            "predictive_confidence": 0.8,
            "ensemble_confidence": 0.8,
            "trade": True,
        }
        payload = engine.dashboard_payload([candidate], [])
        opportunity = payload["opportunities"][0]
        assert opportunity["net_edge"] == pytest.approx(0.20)
        assert opportunity["expected_net_roi"] == pytest.approx(0.20)
        assert opportunity["lcb_roic"] == pytest.approx(0.05)
        assert opportunity["net_edge"] != opportunity["lcb_roic"]
    finally:
        engine.close()
