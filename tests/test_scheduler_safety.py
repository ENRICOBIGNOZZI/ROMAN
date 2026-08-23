from roman_arb.scheduler import AdaptiveQueryScheduler


def test_standard_scheduler_schema_does_not_crash_forward_outcome_hook(tmp_path):
    s = AdaptiveQueryScheduler(str(tmp_path / "tracking.sqlite"))
    try:
        assert s.record_forward_outcomes() == 0
    finally:
        s.close()


def test_candidate_feedback_updates_query_reward_once(tmp_path):
    s = AdaptiveQueryScheduler(str(tmp_path / "tracking.sqlite"))
    c = {
        "buy_source": "ebay",
        "buy_query": "LEGO 75192",
        "entity_key": "lego:75192",
        "buy_external_id": "1",
        "exit_source": "stockx",
        "score_per_capital_day": 0.01,
        "fdr_selected": True,
    }
    try:
        s.record_scan("ebay", "LEGO 75192", 10)
        s.record_candidates([c])
        s.record_candidates([c])
        board = s.leaderboard()
        assert len(board) == 1
        assert board[0]["signals"] == 1
        assert board[0]["selected"] == 1
        assert abs(board[0]["reward_sum"] - 0.01) < 1e-12
    finally:
        s.close()
