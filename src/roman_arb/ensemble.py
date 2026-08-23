"""Deprecated compatibility import for the pre-unification ensemble.

The live/core decision path does not import this module.  The implementation is
kept under :mod:`roman_arb.experimental.legacy_ensemble` only so historical
experiments and old imports remain reproducible.
"""

from .experimental.legacy_ensemble import ConservativeEnsemble, EnsembleDecision

__all__ = ["ConservativeEnsemble", "EnsembleDecision"]
