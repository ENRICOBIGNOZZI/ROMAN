from roman_arb.pure_arbitrage import ArbitrageLeg, PureArbitrageEngine


def test_profitable_cross_venue_arbitrage_is_detected():
    engine = PureArbitrageEngine(min_locked_roi=0.01, min_conservative_roi=0.005, min_success_prob=0.70)
    buy = ArbitrageLeg(
        venue="A",
        side="buy",
        executable_price=100.0,
        fee_rate=0.01,
        shipping=2.0,
        fill_prob=0.99,
        stale_ms=100.0,
        latency_ms=50.0,
    )
    sell = ArbitrageLeg(
        venue="B",
        side="sell",
        executable_price=120.0,
        fee_rate=0.02,
        shipping=2.0,
        fill_prob=0.99,
        stale_ms=100.0,
        latency_ms=50.0,
    )

    opp = engine.evaluate_pair(entity_key="item", buy_leg=buy, sell_leg=sell)

    assert opp.executable
    assert opp.reason == "pure_locked_arbitrage"
    assert opp.locked_profit > 0
    assert opp.locked_net_roi > 0.01
    assert opp.conservative_net_roi > 0.005


def test_gross_spread_that_disappears_after_costs_is_rejected():
    engine = PureArbitrageEngine(min_locked_roi=0.001)
    buy = ArbitrageLeg(
        venue="A",
        side="buy",
        executable_price=100.0,
        fee_rate=0.03,
        shipping=5.0,
    )
    sell = ArbitrageLeg(
        venue="B",
        side="sell",
        executable_price=106.0,
        fee_rate=0.03,
        shipping=5.0,
    )

    opp = engine.evaluate_pair(entity_key="item", buy_leg=buy, sell_leg=sell)

    assert not opp.executable
    assert opp.locked_profit < 0
    assert opp.reason == "negative_net_spread"


def test_stale_quote_is_not_called_pure_arbitrage():
    engine = PureArbitrageEngine(max_stale_ms=1_000.0, min_success_prob=0.0)
    buy = ArbitrageLeg(venue="A", side="buy", executable_price=100.0, stale_ms=2_000.0)
    sell = ArbitrageLeg(venue="B", side="sell", executable_price=130.0, stale_ms=100.0)

    opp = engine.evaluate_pair(entity_key="item", buy_leg=buy, sell_leg=sell)

    assert not opp.executable
    assert opp.reason == "stale_quote"


def test_low_fill_probability_is_rejected():
    engine = PureArbitrageEngine(min_success_prob=0.8)
    buy = ArbitrageLeg(venue="A", side="buy", executable_price=100.0, fill_prob=0.5)
    sell = ArbitrageLeg(venue="B", side="sell", executable_price=130.0, fill_prob=0.9)

    opp = engine.evaluate_pair(entity_key="item", buy_leg=buy, sell_leg=sell)

    assert not opp.executable
    assert opp.reason == "execution_probability_too_low"


def test_engine_uses_minimum_executable_quantity():
    engine = PureArbitrageEngine(min_success_prob=0.0)
    buy = ArbitrageLeg(venue="A", side="buy", executable_price=100.0, available_qty=3.0)
    sell = ArbitrageLeg(venue="B", side="sell", executable_price=120.0, available_qty=1.5)

    opp = engine.evaluate_pair(entity_key="item", buy_leg=buy, sell_leg=sell)

    assert opp.quantity == 1.5


def test_same_venue_pair_is_rejected():
    engine = PureArbitrageEngine(min_success_prob=0.0)
    buy = ArbitrageLeg(venue="A", side="buy", executable_price=100.0)
    sell = ArbitrageLeg(venue="A", side="sell", executable_price=120.0)

    opp = engine.evaluate_pair(entity_key="item", buy_leg=buy, sell_leg=sell)

    assert not opp.executable
    assert opp.reason == "same_venue"


def test_market_scan_ranks_by_conservative_return_per_capital_day():
    engine = PureArbitrageEngine(min_success_prob=0.0)
    books = {
        "x": {
            "buys": [ArbitrageLeg(venue="A", side="buy", executable_price=100.0)],
            "sells": [ArbitrageLeg(venue="B", side="sell", executable_price=120.0)],
        },
        "y": {
            "buys": [ArbitrageLeg(venue="A", side="buy", executable_price=100.0)],
            "sells": [ArbitrageLeg(venue="C", side="sell", executable_price=130.0)],
        },
    }

    opps = engine.scan_market(books)

    assert [o.entity_key for o in opps] == ["y", "x"]
