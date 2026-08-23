from roman_arb.model_stack import SimpleModelStack


def test_expected_exit_uses_selected_route_not_cross_market_fair_with_route_fee():
    m = SimpleModelStack(min_lcb_roi=0.001, lcb_z=0.5)
    out = m.score({
        "buy_price": 100.0,
        "base_fair_value": 200.0,
        "sector": "cards",
        "title": "sealed authenticated full set",
        "exit_source": "cheap-fee-route",
        "exit_fee_rate": 0.0,
        "exit_fixed": 0.0,
        "exit_shipping": 0.0,
        "model_sigma_roi": 0.001,
        "comparables_net": [
            {
                "source": "expensive-market",
                "net_value": 180.0,
                "freshness": 1.0,
                "executable_confidence": 0.8,
            },
            {
                "source": "cheap-fee-route",
                "net_value": 110.0,
                "freshness": 1.0,
                "executable_confidence": 0.8,
            },
        ],
    })
    # Fair value remains a valuation state, but PnL is tied to the selected route.
    assert out.fair_value == 200.0
    assert abs(out.expected_exit_net - 110.0) < 1e-12
    assert abs(out.fair_value_net_roi - 0.10) < 1e-12


def test_additional_operational_losses_are_subtracted_after_route_net():
    m = SimpleModelStack(min_lcb_roi=0.001, lcb_z=0.5)
    out = m.score({
        "buy_price": 100.0,
        "base_fair_value": 130.0,
        "sector": "cards",
        "title": "sealed authenticated full set",
        "exit_source": "route",
        "expected_fraud_loss": 2.0,
        "expected_return_loss": 1.0,
        "comparables_net": [
            {
                "source": "route",
                "net_value": 115.0,
                "freshness": 1.0,
                "executable_confidence": 0.8,
            }
        ],
    })
    assert abs(out.expected_exit_net - 112.0) < 1e-12
