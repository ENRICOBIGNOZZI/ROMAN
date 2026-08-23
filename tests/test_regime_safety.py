from roman_arb.regime import RegimeDetector


def test_regime_detector_catches_persistent_negative_shift():
    r = RegimeDetector(
        alpha=0.05,
        ph_drift=0.0005,
        ph_threshold=0.018,
        stress_hold_updates=4,
    )
    for _ in range(50):
        r.update("market", 0.0)
    assert not r.estimate("market").stressed

    seen = False
    for _ in range(8):
        seen = seen or r.update("market", -0.006).stressed
    assert seen


def test_regime_stress_has_short_persistence_then_recovers():
    r = RegimeDetector(stress_hold_updates=3)
    for _ in range(40):
        r.update("market", 0.0)
    shocked = r.update("market", -0.15)
    assert shocked.stressed

    # One quiet observation must not immediately restore full model weight.
    assert r.update("market", 0.0).stressed

    for _ in range(20):
        last = r.update("market", 0.0)
    assert not last.stressed
