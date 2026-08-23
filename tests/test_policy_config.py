from roman_arb.config import load_config


def test_default_maximal_universe_uses_markets_risk_policy_overlay():
    assumptions, _, sectors = load_config()
    assert len(sectors) >= 300
    assert assumptions["cash_buffer_fraction"] == 0.20
    assert assumptions["forced_liquidation_days"] == 45
