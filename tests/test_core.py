from roman_arb.config import load_config
from roman_arb.fees import FeeEngine
from roman_arb.simulator import run_simulation


def test_config_has_20_sectors():
    _, venues, sectors = load_config()
    assert len(sectors) == 20
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
