import json

from roman_arb.config import load_config, policy_config_path


def test_default_maximal_universe_uses_markets_risk_policy_overlay():
    assumptions, venues, sectors = load_config()
    policy = json.loads(policy_config_path().read_text())

    assert len(sectors) >= 300
    assert assumptions["cash_buffer_fraction"] == 0.20
    assert assumptions["forced_liquidation_days"] == 45

    # markets.json is the live policy source for venue economics even when the
    # broader universe comes from the packed maximal catalog.
    for key, row in policy["venues"].items():
        assert key in venues
        assert venues[key].sell_fee == float(row.get("sell_fee", 0.0))
        assert venues[key].fixed_exit == float(row.get("fixed_exit", 0.0))
        assert venues[key].price_haircut == float(row.get("price_haircut", 0.0))

    # Regenerating the maximal catalogue must never drop a core policy sector
    # that live routing/aliases rely on.
    for row in policy["sectors"]:
        assert row["key"] in sectors
    assert "retro_games" in sectors
    assert "consoles" in sectors
