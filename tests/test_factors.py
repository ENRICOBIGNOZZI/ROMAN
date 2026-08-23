import numpy as np

from roman_arb.factors import RobustPCAFactorModel, residual_discount_overlay


def test_factor_model_removes_common_move():
    rng = np.random.default_rng(7)
    n = 160
    common = rng.normal(0.0, 0.01, size=n)
    x = np.column_stack([
        1.00 * common + rng.normal(0, 0.0015, n),
        0.85 * common + rng.normal(0, 0.0015, n),
        1.10 * common + rng.normal(0, 0.0015, n),
        0.70 * common + rng.normal(0, 0.0015, n),
        1.25 * common + rng.normal(0, 0.0015, n),
    ])
    m = RobustPCAFactorModel(max_rank=2, variance_target=0.60, min_rows=24, min_series=4)
    fit = m.fit(x, ["a", "b", "c", "d", "e"])
    assert fit is not None
    assert fit.rank >= 1
    assert float(np.sum(fit.explained_variance_ratio)) > 0.5

    # Latest observation contains a common rally plus an idiosyncratic drop in c.
    latest = {"a": 0.010, "b": 0.008, "c": -0.025, "d": 0.007, "e": 0.012}
    sig = {s.name: s for s in m.signals(latest)}
    assert "c" in sig
    assert sig["c"].residual_z < 0
    assert sig["c"].confidence > 0.5


def test_pca_uses_identical_train_and_live_centering_with_drift():
    rng = np.random.default_rng(11)
    n = 220
    offsets = np.array([0.010, 0.015, 0.020, 0.025, 0.030])
    loadings = np.array([1.0, 0.8, 1.2, 0.7, 1.1])
    common = rng.normal(0.0, 0.006, size=n)
    x = offsets + common[:, None] * loadings[None, :] + rng.normal(0.0, 0.0008, size=(n, 5))

    m = RobustPCAFactorModel(max_rank=2, variance_target=0.60, min_rows=24, min_series=4)
    fit = m.fit(x, list("abcde"))
    assert fit is not None

    # At the unconditional location there should be no large fake residual just
    # because each series has a non-zero mean return.
    sig = m.signals(dict(zip("abcde", offsets)))
    assert len(sig) == 5
    assert max(abs(s.residual_return) for s in sig) < 0.004


def test_sparse_latest_cross_section_shrinks_factor_confidence():
    rng = np.random.default_rng(13)
    x = rng.normal(0.0, 0.01, size=(120, 6))
    m = RobustPCAFactorModel(max_rank=2, min_rows=24, min_series=4)
    assert m.fit(x, list("abcdef")) is not None
    full = m.signals({k: 0.001 for k in "abcdef"})
    sparse = m.signals({k: 0.001 for k in "abcd"})
    assert full and sparse
    assert sparse[0].confidence < full[0].confidence


def test_short_history_disables_factor_signal():
    x = np.ones((5, 5)) * 0.001
    m = RobustPCAFactorModel(min_rows=12, min_series=4)
    assert m.fit(x, list("abcde")) is None
    assert m.signals({"a": 0.01}) == []


def test_pca_overlay_is_bounded_and_cannot_create_large_alpha():
    d = residual_discount_overlay(0.01, residual_z=-8.0, confidence=1.0, max_adjustment=0.025)
    assert 0.0349 <= d <= 0.0351
    d2 = residual_discount_overlay(0.01, residual_z=-8.0, confidence=0.0, max_adjustment=0.025)
    assert d2 == 0.01
