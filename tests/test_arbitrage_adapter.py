from roman_arb.arbitrage_adapter import build_executable_books, scan_executable_rows
from roman_arb.pure_arbitrage import PureArbitrageEngine


def test_listing_price_alone_never_creates_pure_arbitrage():
    rows = [
        {"entity_key": "x", "source": "A", "price": 100.0},
        {"entity_key": "x", "source": "B", "price": 150.0},
    ]

    books = build_executable_books(rows)

    assert books["x"]["buys"] == []
    assert books["x"]["sells"] == []


def test_executable_ask_and_bid_create_cross_venue_candidate():
    rows = [
        {
            "entity_key": "x",
            "source": "A",
            "executable_ask": 100.0,
            "buy_fee_rate": 0.01,
            "buy_shipping": 1.0,
            "fill_prob": 0.99,
        },
        {
            "entity_key": "x",
            "source": "B",
            "executable_bid": 120.0,
            "sell_fee_rate": 0.01,
            "sell_shipping": 1.0,
            "fill_prob": 0.99,
        },
    ]
    engine = PureArbitrageEngine(min_success_prob=0.5)

    opps = scan_executable_rows(rows, engine)

    assert len(opps) == 1
    assert opps[0].entity_key == "x"
    assert opps[0].buy_leg.venue == "A"
    assert opps[0].sell_leg.venue == "B"
    assert opps[0].executable
