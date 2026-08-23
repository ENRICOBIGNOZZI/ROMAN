from roman_arb.ensemble import ConservativeEnsemble


def test_positive_fair_and_anomaly_are_not_two_independent_votes():
    e = ConservativeEnsemble(min_signal_roi=0.004)
    d = e.decide(
        fair_value_roi=0.20,
        factor_roi=None,
        anomaly_roi=0.18,
        seller_success_prob=0.8,
        condition_risk=0.1,
        sale_prob_30d=0.8,
        regime_weight=1.0,
    )
    assert not d.trade
    assert d.reason == "insufficient_independent_confirmation"


def test_factor_must_add_positive_temporal_information():
    e = ConservativeEnsemble(min_signal_roi=0.004)
    copied = e.decide(
        fair_value_roi=0.20,
        factor_roi=0.20,
        anomaly_roi=0.18,
        seller_success_prob=0.8,
        condition_risk=0.1,
        sale_prob_30d=0.8,
        regime_weight=1.0,
    )
    assert not copied.trade
    assert copied.reason == "insufficient_independent_confirmation"

    confirmed = e.decide(
        fair_value_roi=0.20,
        factor_roi=0.205,
        anomaly_roi=0.18,
        seller_success_prob=0.8,
        condition_risk=0.1,
        sale_prob_30d=0.8,
        regime_weight=1.0,
    )
    assert confirmed.trade
    assert confirmed.reason == "model_consensus"


def test_locked_executable_route_does_not_need_factor_confirmation():
    e = ConservativeEnsemble(min_signal_roi=0.004)
    d = e.decide(
        fair_value_roi=0.02,
        factor_roi=None,
        anomaly_roi=None,
        locked_spread_roi=0.08,
        seller_success_prob=0.8,
        condition_risk=0.1,
        sale_prob_30d=0.0,
        regime_weight=1.0,
    )
    assert d.trade
    assert d.reason == "locked_executable"
