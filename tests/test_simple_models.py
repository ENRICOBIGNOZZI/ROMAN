import numpy as np

from roman_arb.hierarchy import HierarchicalFairValueModel
from roman_arb.kalman import LocalLevelKalman
from roman_arb.liquidity import SaleHazardModel
from roman_arb.seller import SellerQualityModel
from roman_arb.condition_model import ConditionRiskModel
from roman_arb.regime import RegimeDetector
from roman_arb.ensemble import ConservativeEnsemble
from roman_arb.model_stack import SimpleModelStack
from roman_arb.anomaly import CrossMarketAnomalyModel
from roman_arb.allocator import CapitalDayAllocator


def test_hierarchical_fair_value_shrinks_sparse_product():
    m = HierarchicalFairValueModel()
    for p in [100, 101, 99, 102, 98, 100, 101, 99] * 4:
        m.update(p, "cards", "pokemon", "")
    m.update(140, "cards", "pokemon", "rare-card")
    est = m.predict("cards", "pokemon", "rare-card")
    assert est is not None
    assert 100 < est.price < 140
    assert est.confidence < 0.5


def test_kalman_smooths_observation():
    k = LocalLevelKalman(process_var=1e-5, obs_var=1e-3)
    k.update(0.0)
    for _ in range(10):
        k.update(0.01)
    assert 0.0 < k.predict().mean < 0.011


def test_hazard_discount_sells_faster():
    h = SaleHazardModel()
    base = h.estimate("lego", price_gap=0.0)
    cheap = h.estimate("lego", price_gap=-0.10)
    assert cheap.expected_days < base.expected_days
    assert cheap.prob_30d > base.prob_30d


def test_seller_posterior_learns():
    s = SellerQualityModel()
    before = s.estimate("seller-a").success_prob
    for _ in range(8):
        s.update("seller-a", True, 0.02)
    after = s.estimate("seller-a")
    assert after.success_prob > before
    assert after.risk_penalty_roi < s.estimate("new-seller").risk_penalty_roi


def test_condition_text_penalizes_damage():
    m = ConditionRiskModel()
    good = m.score("sealed authenticated full set", image_count=8)
    bad = m.score("damaged cracked untested as-is", image_count=1, image_defect_score=0.8)
    assert bad.risk > good.risk
    assert bad.haircut > good.haircut


def test_regime_detector_reduces_weight_after_shock():
    r = RegimeDetector()
    for _ in range(40):
        r.update("watches", 0.001)
    normal = r.estimate("watches")
    shocked = r.update("watches", -0.15)
    assert shocked.weight < normal.weight


def test_ensemble_requires_agreement_unless_locked():
    e = ConservativeEnsemble(min_signal_roi=0.005)
    no = e.decide(0.03, -0.01, None, seller_success_prob=0.8, condition_risk=0.1, sale_prob_30d=0.8)
    assert not no.trade
    locked = e.decide(None, None, None, locked_spread_roi=0.04, seller_success_prob=0.8, condition_risk=0.1, sale_prob_30d=0.8)
    assert locked.trade


def test_model_stack_is_net_of_fees_and_costs():
    s = SimpleModelStack(min_lcb_roi=0.002, lcb_z=1.0)
    for _ in range(8):
        s.sellers.update("seller-a", True, 0.02)
    gross = {
        "buy_price": 100.0,
        "base_fair_value": 120.0,
        "sector": "cards",
        "family": "pokemon",
        "product": "x",
        "title": "sealed authenticated",
        "seller_route_key": "seller-a",
        "locked_exit_bid": 120.0,
        "model_sigma_roi": 0.001,
    }
    cheap_costs = s.score(dict(gross, exit_fee_rate=0.02, exit_shipping=1.0))
    high_costs = s.score(dict(gross, exit_fee_rate=0.15, exit_shipping=7.0, authentication_cost=3.0))
    assert cheap_costs.locked_net_roi > high_costs.locked_net_roi
    assert cheap_costs.lcb_net_roi > high_costs.lcb_net_roi


def test_factor_overlay_stays_bounded():
    from roman_arb.factors import residual_discount_overlay
    assert residual_discount_overlay(0.0, -100.0, 1.0) <= 0.0250001
    assert residual_discount_overlay(0.0, 100.0, 1.0) >= -0.0250001


def test_anomaly_model_downweights_stale_comparables():
    m = CrossMarketAnomalyModel(min_comparables=3)
    fresh = m.score(100, [
        {"net_value": 120, "freshness": 1, "executable_confidence": 1},
        {"net_value": 121, "freshness": 1, "executable_confidence": 1},
        {"net_value": 119, "freshness": 1, "executable_confidence": 1},
    ])
    stale = m.score(100, [
        {"net_value": 120, "freshness": 0.1, "executable_confidence": 0.2},
        {"net_value": 121, "freshness": 0.1, "executable_confidence": 0.2},
        {"net_value": 119, "freshness": 0.1, "executable_confidence": 0.2},
    ])
    assert fresh is not None and stale is not None
    assert fresh.confidence > stale.confidence


def test_dynamic_factor_adjustment_is_bounded_inside_stack():
    s = SimpleModelStack(min_lcb_roi=0.001, lcb_z=0.5)
    s.update_dynamic_factors({"market": 0.01})
    s.update_dynamic_factors({"market": 0.012})
    for _ in range(8):
        s.sellers.update("seller", True, 0.02)
    out = s.score({
        "buy_price": 100,
        "base_fair_value": 120,
        "sector": "sneakers",
        "title": "new authenticated",
        "seller_route_key": "seller",
        "exit_fee_rate": 0.02,
        "factor_loadings": {"market": 1.0},
        "item_return": -0.20,
        "model_sigma_roi": 0.001,
    })
    assert out.factor_net_roi is not None
    assert abs(out.factor_net_roi - out.fair_value_net_roi) <= 0.0200001


def test_allocator_respects_10k_cash_buffer_and_item_cap():
    a = CapitalDayAllocator(capital=10000, cash_buffer_fraction=0.10)
    rows = [
        {"trade": True, "entity_key": "a", "sector": "cards", "buy_source": "ebay", "acquisition_cost": 2500, "lcb_net_roi": 0.04, "expected_holding_days": 8, "score_per_capital_day": 0.005},
        {"trade": True, "entity_key": "b", "sector": "lego", "buy_source": "bricklink", "acquisition_cost": 2500, "lcb_net_roi": 0.03, "expected_holding_days": 10, "score_per_capital_day": 0.003},
        {"trade": True, "entity_key": "c", "sector": "watches", "buy_source": "chrono24", "acquisition_cost": 5000, "lcb_net_roi": 0.05, "expected_holding_days": 15, "score_per_capital_day": 0.0033},
    ]
    r = a.allocate(rows)
    assert r.capital_used <= 9000.0001
    assert all(float(x["acquisition_cost"]) <= 3000.0001 for x in r.selected)
