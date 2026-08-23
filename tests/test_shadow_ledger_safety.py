from roman_arb.shadow_ledger import ShadowLedger


def _entry(entity: str = "e") -> dict:
    return {
        "entity_key": entity,
        "acquisition_cost": 100.0,
        "lcb_net_roi": 0.02,
        "expected_holding_days": 10.0,
        "buy_external_id": "entry",
        "buy_source": "buy",
        "exit_source": "exit",
        "locked": False,
    }


def test_executable_value_uses_current_quote_value_not_historical_cost_times_current_roi(tmp_path):
    ledger = ShadowLedger(str(tmp_path / "ledger.sqlite"), capital=1000.0)
    try:
        assert ledger.open_selected([_entry()]) == 1
        # Current candidate denominator is 80. A +25% locked ROI therefore means
        # EUR 100 executable proceeds, not 100 historical entry * 1.25 = 125.
        ledger.mark([
            {
                "entity_key": "e",
                "acquisition_cost": 80.0,
                "locked": True,
                "locked_net_roi": 0.25,
                "expected_exit_net": 98.0,
                "score_per_capital_day": 0.01,
                "exit_source": "route-a",
            }
        ])
        p = ledger.open_positions()[0]
        _, exe = ledger.latest_mark(p["position_id"])
        assert exe is not None
        assert abs(exe - 100.0) < 1e-12
    finally:
        ledger.close()


def test_open_position_is_marked_against_best_current_exit_not_best_new_buy_score(tmp_path):
    ledger = ShadowLedger(str(tmp_path / "ledger.sqlite"), capital=1000.0)
    try:
        assert ledger.open_selected([_entry()]) == 1
        ledger.mark([
            {
                "entity_key": "e",
                "acquisition_cost": 80.0,
                "locked": True,
                "locked_net_roi": 0.25,
                "expected_exit_net": 105.0,
                "score_per_capital_day": 0.02,
                "exit_source": "route-a",
            },
            {
                "entity_key": "e",
                "acquisition_cost": 90.0,
                "locked": True,
                "locked_net_roi": 1.0 / 3.0,
                "expected_exit_net": 120.0,
                "score_per_capital_day": 0.005,
                "exit_source": "route-b",
            },
        ])
        p = ledger.open_positions()[0]
        mark, exe = ledger.latest_mark(p["position_id"])
        assert abs(mark - 120.0) < 1e-12
        assert exe is not None and abs(exe - 120.0) < 1e-10
    finally:
        ledger.close()
