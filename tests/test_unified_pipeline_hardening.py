import pytest

from roman_arb.model_stack import SimpleModelStack


def test_legacy_precomputed_rois_cannot_drive_unified_decision():
    model = SimpleModelStack()
    candidate = {
        "buy_price": 100.0,
        "base_fair_value": 120.0,
        "target_exit_price": 120.0,
        "sector": "cards",
        "title": "authenticated",
        "model_sigma_roi": 0.01,
    }
    base = model.predict(candidate)
    legacy = model.predict(
        dict(
            candidate,
            factor_net_roi=9.0,
            anomaly_net_roi=9.0,
            cross_market_net_roi=9.0,
            locked_net_roi=9.0,
        )
    )
    assert base is not None and legacy is not None
    assert legacy.expected_exit_net == pytest.approx(base.expected_exit_net)
    assert legacy.expected_net_roi == pytest.approx(base.expected_net_roi)
    assert legacy.factor_net_roi is None
    assert legacy.anomaly_net_roi is None
    assert legacy.locked_net_roi is None


def test_locked_legacy_roi_requires_explicit_locked_flag():
    model = SimpleModelStack()
    common = {
        "buy_price": 100.0,
        "base_fair_value": 110.0,
        "sector": "cards",
        "title": "authenticated",
    }
    unlocked = model.predict(dict(common, locked_net_roi=0.50))
    locked = model.predict(dict(common, locked_net_roi=0.50, locked=True))
    assert unlocked is not None and locked is not None
    assert unlocked.locked_net_roi is None
    assert locked.locked_net_roi == pytest.approx(0.50)
    assert locked.expected_holding_days == pytest.approx(1.0)


def test_realized_trade_pnl_does_not_become_seller_quality_label():
    model = SimpleModelStack()
    model.observe_execution(
        exit_price=120.0,
        sector="cards",
        family="graded",
        product="x",
        seller_route_key="seller-x",
        sold=True,
        exposure_days=3.0,
        realized_pnl_roi=-0.25,
    )
    assert model.hierarchy.global_stat.n == 1
    assert "seller-x" not in model.sellers.stats


def test_explicit_seller_quality_label_updates_posterior():
    model = SimpleModelStack()
    before = model.sellers.estimate("seller-x").success_prob
    model.observe_execution(
        exit_price=120.0,
        sector="cards",
        seller_route_key="seller-x",
        sold=True,
        seller_success=True,
    )
    after = model.sellers.estimate("seller-x").success_prob
    assert after > before


def test_conservative_compatibility_field_is_the_actual_lcb():
    model = SimpleModelStack(lcb_z=1.28)
    score = model.score(
        {
            "buy_price": 100.0,
            "base_fair_value": 125.0,
            "target_exit_price": 125.0,
            "sector": "cards",
            "title": "authenticated",
            "model_sigma_roi": 0.01,
        }
    )
    assert score.conservative_net_roi == pytest.approx(score.lcb_net_roi)
    assert score.predictive_confidence == pytest.approx(score.ensemble_confidence)
