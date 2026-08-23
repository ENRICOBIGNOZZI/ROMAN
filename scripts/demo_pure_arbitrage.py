from roman_arb.arbitrage_adapter import scan_executable_rows
from roman_arb.pure_arbitrage import PureArbitrageEngine


if __name__ == "__main__":
    rows = [
        {
            "entity_key": "demo-item",
            "source": "venue-a",
            "executable_ask": 100.0,
            "buy_fee_rate": 0.01,
            "buy_shipping": 2.0,
            "available_qty": 1.0,
            "fill_prob": 0.99,
            "stale_ms": 100.0,
            "latency_ms": 50.0,
        },
        {
            "entity_key": "demo-item",
            "source": "venue-b",
            "executable_bid": 120.0,
            "sell_fee_rate": 0.02,
            "sell_shipping": 2.0,
            "available_qty": 1.0,
            "fill_prob": 0.99,
            "stale_ms": 100.0,
            "latency_ms": 50.0,
        },
    ]

    engine = PureArbitrageEngine()
    for opp in scan_executable_rows(rows, engine):
        print(
            opp.entity_key,
            opp.buy_leg.venue,
            "->",
            opp.sell_leg.venue,
            f"profit={opp.locked_profit:.2f}",
            f"locked_roi={opp.locked_net_roi:.2%}",
            f"conservative_roi={opp.conservative_net_roi:.2%}",
            f"success_prob={opp.success_prob:.2%}",
        )
