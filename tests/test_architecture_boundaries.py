import inspect
from pathlib import Path

import roman_arb.daemon as daemon
import roman_arb.live as live
import roman_arb.model_stack as model_stack
from roman_arb.ensemble import ConservativeEnsemble
from roman_arb.production import ShadowLiveEngine as ProductionShadowLiveEngine
from roman_arb.unified_model import SimpleModelStack


def test_live_entrypoint_reaches_only_unified_decision_stack():
    daemon_source = inspect.getsource(daemon)
    live_source = inspect.getsource(live)
    stack_source = inspect.getsource(model_stack)

    assert daemon.ShadowLiveEngine is ProductionShadowLiveEngine
    assert "unified_model" in stack_source
    assert model_stack.SimpleModelStack is SimpleModelStack

    forbidden_live_dependencies = (
        "ConservativeEnsemble",
        "from .strategy",
        "from .portfolio",
        "from .simulator",
        "from .experimental",
    )
    for token in forbidden_live_dependencies:
        assert token not in live_source


def test_manual_live_launchers_delegate_to_canonical_daemon():
    for path in ("scripts/run_live.py", "scripts/run_live_daemon.py"):
        source = Path(path).read_text()
        assert "roman_arb.daemon import main" in source
        assert "PosteriorFDRSelector" not in source
        assert "PaperEngine" not in source


def test_legacy_ensemble_is_quarantined_under_experimental_namespace():
    assert ConservativeEnsemble.__module__ == "roman_arb.experimental.legacy_ensemble"
