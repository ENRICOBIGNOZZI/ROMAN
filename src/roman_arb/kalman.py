from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass
class LocalLevelState:
    mean: float = 0.0
    variance: float = 1.0
    initialized: bool = False


class LocalLevelKalman:
    """Minimal local-level Kalman filter for a drifting latent return/factor."""

    def __init__(self, process_var: float = 2.5e-5, obs_var: float = 2.5e-4):
        self.q = float(process_var)
        self.r = float(obs_var)
        self.state = LocalLevelState()

    def update(self, y: float) -> LocalLevelState:
        if not math.isfinite(y):
            return self.state
        s = self.state
        if not s.initialized:
            s.mean = float(y)
            s.variance = max(self.r, 1e-9)
            s.initialized = True
            return s
        pred_var = s.variance + self.q
        k = pred_var / (pred_var + self.r)
        s.mean = s.mean + k * (float(y) - s.mean)
        s.variance = max((1.0 - k) * pred_var, 1e-12)
        return s

    def predict(self) -> LocalLevelState:
        s = self.state
        if not s.initialized:
            return s
        return LocalLevelState(mean=s.mean, variance=s.variance + self.q, initialized=True)


class DynamicFactorLayer:
    """One independent local-level filter per PCA/market factor.

    This keeps the dynamic layer transparent: PCA supplies factor returns and the
    Kalman filters estimate their current latent state.  A product-level common
    return is obtained from externally estimated loadings.
    """

    def __init__(self, process_var: float = 2.5e-5, obs_var: float = 2.5e-4):
        self.process_var = float(process_var)
        self.obs_var = float(obs_var)
        self.filters: dict[str, LocalLevelKalman] = {}

    def update(self, factor_returns: dict[str, float]) -> dict[str, LocalLevelState]:
        out = {}
        for name, value in factor_returns.items():
            f = self.filters.setdefault(name, LocalLevelKalman(self.process_var, self.obs_var))
            out[name] = f.update(float(value))
        return out

    def current(self) -> dict[str, float]:
        return {k: v.predict().mean for k, v in self.filters.items() if v.state.initialized}

    def common_return(self, loadings: dict[str, float]) -> tuple[float, float]:
        mean = 0.0
        var = 0.0
        used = 0
        for name, beta in loadings.items():
            f = self.filters.get(name)
            if f is None or not f.state.initialized:
                continue
            p = f.predict()
            b = float(beta)
            mean += b * p.mean
            var += b * b * p.variance
            used += 1
        return mean, math.sqrt(max(var, 0.0)) if used else 0.0
