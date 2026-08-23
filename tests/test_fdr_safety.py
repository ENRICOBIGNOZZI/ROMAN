from roman_arb.fdr import PosteriorFDRSelector


def test_fdr_selects_only_one_exact_route_per_entity():
    rows = [
        {
            "trade": True,
            "entity_key": "same-item",
            "buy_source": "a",
            "buy_external_id": "1",
            "exit_source": "x",
            "score_per_capital_day": 0.010,
            "lcb_net_roi": 0.04,
            "ensemble_confidence": 0.90,
            "reason": "ok",
        },
        {
            "trade": True,
            "entity_key": "same-item",
            "buy_source": "b",
            "buy_external_id": "2",
            "exit_source": "y",
            "score_per_capital_day": 0.005,
            "lcb_net_roi": 0.03,
            "ensemble_confidence": 0.99,
            "reason": "ok",
        },
        {
            "trade": True,
            "entity_key": "other-item",
            "buy_source": "c",
            "buy_external_id": "3",
            "exit_source": "z",
            "score_per_capital_day": 0.008,
            "lcb_net_roi": 0.03,
            "ensemble_confidence": 0.90,
            "reason": "ok",
        },
    ]
    s = PosteriorFDRSelector(alpha=0.20)
    result = s.annotate(rows)
    assert len(result.selected) == 2
    assert rows[0]["fdr_selected"]
    assert not rows[1]["fdr_selected"]
    assert rows[2]["fdr_selected"]


def test_fdr_rejects_nonfinite_confidence():
    rows = [{
        "trade": True,
        "entity_key": "x",
        "buy_source": "a",
        "buy_external_id": "1",
        "exit_source": "b",
        "score_per_capital_day": 0.01,
        "lcb_net_roi": 0.05,
        "ensemble_confidence": float("nan"),
    }]
    r = PosteriorFDRSelector(alpha=0.25).annotate(rows)
    assert r.selected == ()
    assert not rows[0]["fdr_selected"]
