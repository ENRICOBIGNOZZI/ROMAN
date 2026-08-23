from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class AnomalyEstimate:
    reference_net_value: float
    net_roi: float
    robust_z: float
    confidence: float
    n_comparables: int


class CrossMarketAnomalyModel:
    """Robust same-entity cross-market anomaly detector on net-equivalent values."""

    def __init__(self, min_comparables: int = 3, max_abs_z: float = 8.0):
        self.min_comparables = int(min_comparables)
        self.max_abs_z = float(max_abs_z)

    def score(self, acquisition_cost: float, comparables: list[dict] | list[float]) -> AnomalyEstimate | None:
        vals: list[float] = []
        weights: list[float] = []
        for x in comparables:
            if isinstance(x, dict):
                v = x.get("net_value", x.get("price"))
                try: v = float(v)
                except Exception: continue
                w = float(x.get("weight", 1.0))
                freshness = float(x.get("freshness", 1.0))
                executable = float(x.get("executable_confidence", 1.0))
                w *= max(0.0, min(1.0, freshness)) * max(0.0, min(1.0, executable))
            else:
                try: v = float(x); w = 1.0
                except Exception: continue
            if math.isfinite(v) and v > 0 and w > 0:
                vals.append(v); weights.append(w)
        if len(vals) < self.min_comparables or acquisition_cost <= 0:
            return None

        a = np.asarray(vals, dtype=float)
        w = np.asarray(weights, dtype=float)
        order = np.argsort(a); a = a[order]; w = w[order]
        cw = np.cumsum(w) / max(float(np.sum(w)), 1e-12)
        median = float(a[np.searchsorted(cw, 0.5)])
        abs_dev = np.abs(a - median)
        o2 = np.argsort(abs_dev); d = abs_dev[o2]; w2 = w[o2]
        cw2 = np.cumsum(w2) / max(float(np.sum(w2)), 1e-12)
        mad = float(d[np.searchsorted(cw2, 0.5)])
        scale = max(1.4826 * mad, 0.01 * median, 1e-6)
        z = (float(acquisition_cost) - median) / scale
        z = max(-self.max_abs_z, min(self.max_abs_z, z))
        roi = (median - float(acquisition_cost)) / float(acquisition_cost)
        effective_n = float(np.sum(w))
        dispersion_penalty = 1.0 / (1.0 + scale / max(median, 1e-9) * 8.0)
        confidence = (effective_n / (effective_n + 4.0)) * dispersion_penalty
        return AnomalyEstimate(median, roi, z, max(0.0, min(1.0, confidence)), len(vals))
