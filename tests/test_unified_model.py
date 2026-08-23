import pytest

from roman_arb.model_stack import SimpleModelStack


def _good_seller(model: SimpleModelStack, key: str = "seller-a") -> None:
    for _ in range(10):
        model.sellers.update(key, True, 0.02)


def test_single_predictive_model_does_not_require_model_voting():
    m = SimpleModelStack(min_lcb_roi=0.001, lcb_z=0.5)
    _good_seller(m)
    out = m.score({
        "buy_price": 100.0,
        "base_fair_value": 125.0,
        "target_exit_price": 125.0,
        "sector": "cards",
        "title": "sealed authenticated",
        "seller_route_key": "seller-a",
        "model_sigma_roi": 0.001,
    })
    assert out.factor_net_roi is None
    assert out.anomaly_net_roi is None
    assert out.trade
    assert out.reason == "unified_predictive_lcb"


def test_acquisition_discount_does_not_artificially_speed_up_sale_hazard():
    m = SimpleModelStack()
    common = {
        "base_fair_value": 120.0,
        "target_exit_price": 120.0,
        "sector": "lego",
        "title": "new sealed",
    }
    cheap = m.predict(dict(common, buy_price=80.0))
    expensive = m.predict(dict(common, buy_price=100.0))
    assert cheap is not None and expensive is not None
    assert cheap.expected_holding_days == pytest.approx(expensive.expected_holding_days)
    assert cheap.sale_prob_30d == pytest.approx(expensive.sale_prob_30d)


def test_comparables_update_same_payoff_distribution():
    m = SimpleModelStack()
    base = {
        "buy_price": 100.0,
        "base_fair_value": 110.0,
        "sector": "cards",
        "title": "authenticated",
    }
    p0 = m.predict(base)
    p1 = m.predict(dict(base, comparables_net=[
        {"net_value": 138.0, "freshness": 1.0, "executable_confidence": 1.0},
        {"net_value": 140.0, "freshness": 1.0, "executable_confidence": 1.0},
        {"net_value": 142.0, "freshness": 1.0, "executable_confidence": 1.0},
    ]))
    assert p0 is not None and p1 is not None
    assert p1.anomaly_net_roi is not None
    assert p1.expected_net_roi > p0.expected_net_roi


def test_score_is_lcb_of_the_single_prediction():
    m = SimpleModelStack(min_lcb_roi=0.0, lcb_z=1.28)
    _good_seller(m)
    candidate = {
        "buy_price": 100.0,
        "base_fair_value": 120.0,
        "sector": "sneakers",
        "title": "new authenticated",
        "seller_route_key": "seller-a",
        "model_sigma_roi": 0.01,
    }
    p = m.predict(candidate)
    s = m.score(candidate)
    assert p is not None
    assert s.lcb_net_roi == pytest.approx(p.expected_net_roi - 1.28 * p.sigma_net_roi)
    assert s.score_per_capital_day == pytest.approx(s.lcb_net_roi / p.expected_holding_days)
