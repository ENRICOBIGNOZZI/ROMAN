from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import math
import numpy as np


@dataclass(frozen=True)
class FactorFit:
    names: tuple[str, ...]
    center: np.ndarray
    scale: np.ndarray
    standardized_mean: np.ndarray
    components: np.ndarray
    explained_variance_ratio: np.ndarray
    n_rows: int

    @property
    def rank(self) -> int:
        return int(self.components.shape[0])


@dataclass(frozen=True)
class ResidualSignal:
    name: str
    raw_return: float
    common_return: float
    residual_return: float
    residual_z: float
    confidence: float


class RobustPCAFactorModel:
    """Conservative PCA overlay for *returns*, never raw price levels.

    The model is deliberately an overlay rather than a standalone trading signal.
    It removes common movements from homogeneous return series and reports the
    idiosyncratic residual. Confidence is shrunk toward zero when history is
    short or contemporaneous coverage is sparse, so a newly started shadow run
    cannot manufacture alpha from an underidentified factor model.

    Missing observations should be represented by ``np.nan``. The estimator:
      1. winsorizes each series using median/MAD;
      2. standardizes series robustly;
      3. fills missing standardized returns with zero (the robust center);
      4. stores and removes the remaining time-series mean;
      5. fits PCA via SVD;
      6. chooses the smallest rank reaching ``variance_target`` subject to caps.

    The stored standardized mean is essential: training and live scoring must use
    exactly the same centering transformation. Otherwise unconditional drift can
    leak into the residual and be mistaken for idiosyncratic alpha.
    """

    def __init__(
        self,
        max_rank: int = 6,
        variance_target: float = 0.70,
        min_rows: int = 12,
        min_series: int = 4,
        winsor_z: float = 5.0,
        confidence_half_life_rows: float = 48.0,
    ):
        self.max_rank = int(max_rank)
        self.variance_target = float(variance_target)
        self.min_rows = int(min_rows)
        self.min_series = int(min_series)
        self.winsor_z = float(winsor_z)
        self.confidence_half_life_rows = float(confidence_half_life_rows)
        self.fit_: FactorFit | None = None
        self._resid_scale: np.ndarray | None = None

    @staticmethod
    def _robust_center_scale(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        center = np.nanmedian(x, axis=0)
        mad = np.nanmedian(np.abs(x - center), axis=0)
        # 1.4826 * MAD is a Gaussian-consistent scale estimator.
        scale = 1.4826 * mad
        fallback = np.nanstd(x, axis=0, ddof=1)
        scale = np.where(np.isfinite(scale) & (scale > 1e-8), scale, fallback)
        scale = np.where(np.isfinite(scale) & (scale > 1e-8), scale, 1.0)
        center = np.where(np.isfinite(center), center, 0.0)
        return center.astype(float), scale.astype(float)

    def fit(self, returns: np.ndarray, names: Iterable[str]) -> FactorFit | None:
        x = np.asarray(returns, dtype=float)
        names = tuple(str(n) for n in names)
        if x.ndim != 2 or x.shape[1] != len(names):
            raise ValueError("returns must be a 2D array with one column per name")
        if x.shape[0] < self.min_rows or x.shape[1] < self.min_series:
            self.fit_ = None
            self._resid_scale = None
            return None

        # Require each series to have enough actual observations. This avoids a
        # large sparse universe creating unstable components through zero-filling.
        observed = np.sum(np.isfinite(x), axis=0)
        keep = observed >= max(6, self.min_rows // 3)
        if int(np.sum(keep)) < self.min_series:
            self.fit_ = None
            self._resid_scale = None
            return None
        x = x[:, keep]
        names = tuple(n for n, k in zip(names, keep) if k)

        center, scale = self._robust_center_scale(x)
        z = (x - center) / scale
        z = np.clip(z, -self.winsor_z, self.winsor_z)
        z = np.where(np.isfinite(z), z, 0.0)

        # PCA is a centered covariance model. Store this second-stage mean and
        # reuse it during live scoring; dropping it creates a train/test mismatch.
        standardized_mean = np.mean(z, axis=0)
        z_centered = z - standardized_mean
        _, s, vt = np.linalg.svd(z_centered, full_matrices=False)
        eigen = s * s
        total = float(np.sum(eigen))
        if not math.isfinite(total) or total <= 1e-12:
            self.fit_ = None
            self._resid_scale = None
            return None
        evr = eigen / total
        cumulative = np.cumsum(evr)
        k_target = int(np.searchsorted(cumulative, self.variance_target) + 1)
        # Never allow PCA to explain nearly all cross-sectional dimensions: we
        # need an idiosyncratic residual to remain identifiable.
        max_identified_rank = max(1, x.shape[1] - 2)
        rank = max(1, min(self.max_rank, k_target, max_identified_rank))
        components = vt[:rank].copy()

        fit = FactorFit(
            names=names,
            center=center,
            scale=scale,
            standardized_mean=standardized_mean.copy(),
            components=components,
            explained_variance_ratio=evr[:rank].copy(),
            n_rows=int(x.shape[0]),
        )
        self.fit_ = fit

        fitted = self._common_standardized(z_centered)
        resid = (z_centered - fitted) * scale
        _, resid_scale = self._robust_center_scale(resid)
        self._resid_scale = resid_scale
        return fit

    def _common_standardized(self, standardized_centered: np.ndarray) -> np.ndarray:
        if self.fit_ is None:
            raise RuntimeError("factor model is not fitted")
        c = self.fit_.components
        return (standardized_centered @ c.T) @ c

    def signals(self, latest_returns: dict[str, float]) -> list[ResidualSignal]:
        if self.fit_ is None or self._resid_scale is None:
            return []
        f = self.fit_
        raw = np.array([float(latest_returns.get(n, np.nan)) for n in f.names], dtype=float)
        available = np.isfinite(raw)
        if int(np.sum(available)) < max(2, f.rank):
            return []

        z = (raw - f.center) / f.scale
        z = np.clip(z, -self.winsor_z, self.winsor_z)
        # Missing contemporaneous returns are neutralized at the robust center.
        z_filled = np.where(np.isfinite(z), z, 0.0)
        z_centered = z_filled - f.standardized_mean
        common_centered = self._common_standardized(z_centered[None, :])[0]

        # Reconstruct in raw-return units. Both the robust location and the
        # second-stage PCA mean must be restored before computing the residual.
        common = f.center + (f.standardized_mean + common_centered) * f.scale
        residual = raw - common
        residual_z = residual / np.maximum(self._resid_scale, 1e-8)

        # Sample-size and contemporaneous-coverage shrinkage.
        sample_conf = f.n_rows / (f.n_rows + self.confidence_half_life_rows)
        coverage_conf = float(np.sum(available)) / max(len(available), 1)
        conf = sample_conf * coverage_conf
        out: list[ResidualSignal] = []
        for i, name in enumerate(f.names):
            if not available[i]:
                continue
            rz = float(np.clip(residual_z[i], -8.0, 8.0))
            out.append(
                ResidualSignal(
                    name=name,
                    raw_return=float(raw[i]),
                    common_return=float(common[i]),
                    residual_return=float(residual[i]),
                    residual_z=rz,
                    confidence=float(conf),
                )
            )
        return out


def residual_discount_overlay(
    base_discount: float,
    residual_z: float,
    confidence: float,
    max_adjustment: float = 0.025,
    z_saturation: float = 3.0,
) -> float:
    """Small bounded adjustment to a pre-existing valuation discount.

    A negative residual return means the item/series fell relative to its common
    factors; if the base valuation model already identifies it as cheap, this can
    modestly strengthen the signal. PCA is never allowed to create more than
    ``max_adjustment`` of discount by itself.
    """
    z = float(np.clip(residual_z / max(z_saturation, 1e-9), -1.0, 1.0))
    # Cheap residual => negative z => positive discount adjustment.
    adjustment = -z * float(max_adjustment) * float(np.clip(confidence, 0.0, 1.0))
    return float(base_discount + adjustment)
