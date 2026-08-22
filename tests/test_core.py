from roman_arb.config import load_config
from roman_arb.fees import FeeEngine
from roman_arb.simulator import run_simulation


def test_default_config_is_maximal():
    _, venues, sectors = load_config()
    assert len(sectors) >= 350
    assert len(venues) >= 80
    assert "chrono24" in venues


def test_fee_engine():
    _, venues, _ = load_config()
    f = FeeEngine(venues)
    assert f.net_proceeds(1000, "chrono24") < 1000
    assert f.net_proceeds(1000, "bricklink") > f.net_proceeds(1000, "chrono24")


def test_simulation_cash_realized():
    r = run_simulation(initial_capital=20000, days=30, seed=1)
    assert r.summary["final_cash"] > 0
    assert r.summary["fills"] == r.summary["trades"]


def test_expanded_universe_loads():
    from roman_arb.config import load_config
    _, venues, sectors = load_config("config/markets_expanded.json")
    assert len(sectors) >= 70
    assert len(venues) >= 30
    assert all(s.exit_venues for s in sectors.values())


def test_feed_registry_and_entity():
    from roman_arb.feeds import load_source_registry
    from roman_arb.entity import canonical_title
    r = load_source_registry()
    assert "ebay" in r and "stockx" in r and len(r) >= 190
    assert canonical_title("Rolex Explorer 124270 Full Set") == "rolex explorer 124270"


def test_maximal_universe_loads():
    from roman_arb.config import load_config
    _, venues, sectors = load_config()
    assert len(sectors) >= 300
    assert len(venues) >= 50
    assert any(s.source_venues for s in sectors.values())


def test_live_query_plan_covers_many_sources():
    from roman_arb.live import build_query_plan
    plan = build_query_plan()
    assert len(plan) >= 20
    assert sum(len(v) for v in plan.values()) >= 500
