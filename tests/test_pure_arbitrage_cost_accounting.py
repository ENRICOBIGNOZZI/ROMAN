import pytest

from roman_arb.pure_arbitrage import ArbitrageLeg, PureArbitrageEngine


def test_full_cost_accounting_on_both_legs():
    engine = PureArbitrageEngine(
        min_locked_roi=0.0,
        min_conservative_roi=-1.0,
        min_success_prob=0.0,
        failure_loss_fraction=0.0,
    )
    buy = ArbitrageLeg(
        venue="A",
        side="buy",
        executable_price=100.0,
        fee_rate=0.02,
        fixed_fee=1.0,
        shipping=3.0,
        tax=2.0,
        authentication=1.0,
        fx_cost=0.5,
        other_cost=0.5,
    )
    sell = ArbitrageLeg(
        venue="B",
        side="sell",
        executable_price=130.0,
        fee_rate=0.03,
        fixed_fee=1.0,
        shipping=2.0,
        tax=1.0,
        authentication=1.0,
        fx_cost=0.5,
        other_cost=0.5,
    )

    opp = engine.evaluate_pair(entity_key="item", buy_leg=buy, sell_leg=sell)

    expected_acquisition = 100.0 * 1.02 + 1.0 + 3.0 + 2.0 + 1.0 + 0.5 + 0.5
    expected_exit = 130.0 * 0.97 - 1.0 - 2.0 - 1.0 - 1.0 - 0.5 - 0.5
    expected_profit = expected_exit - expected_acquisition

    assert opp.acquisition_cost == pytest.approx(expected_acquisition)
    assert opp.locked_exit_net == pytest.approx(expected_exit)
    assert opp.locked_profit == pytest.approx(expected_profit)
    assert opp.locked_net_roi == pytest.approx(expected_profit / expected_acquisition)
