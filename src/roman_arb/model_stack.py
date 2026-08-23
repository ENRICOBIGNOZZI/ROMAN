"""Compatibility entrypoint for the unified resale model.

The implementation lives in :mod:`roman_arb.unified_model`.  Existing imports
of ``roman_arb.model_stack.SimpleModelStack`` continue to work unchanged.
"""

from .unified_model import PredictiveDistribution, SimpleModelStack, StackScore

__all__ = ["PredictiveDistribution", "SimpleModelStack", "StackScore"]
