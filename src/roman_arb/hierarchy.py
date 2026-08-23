from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass
class RunningGaussian:
    n: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def update(self, x: float) -> None:
        self.n += 1
        d = x - self.mean
        self.mean += d / self.n
        self.m2 += d * (x - self.mean)

    @property
    def variance(self) -> float:
        return self.m2 / max(self.n - 1, 1)


@dataclass(frozen=True)
class FairValueEstimate:
    price: float
    log_sigma: float
    confidence: float
    effective_n: float


class HierarchicalFairValueModel:
    """Empirical-Bayes hierarchy on trusted executed gross-equivalent prices.

    Hierarchy: product -> family -> sector -> global.
    Each child mean is shrunk toward its parent with n/(n+kappa).

    Persistent learning is deliberately opt-in through ``trusted=True``. Raw asks,
    repeated bid snapshots, model-implied marks and net-of-fee values are not
    independent realized price observations and must not silently increase the
    hierarchy's effective sample size. This is a safety boundary, not just an API
    convenience.
    """

    def __init__(
        self,
        kappa_product: float = 8.0,
        kappa_family: float = 16.0,
        kappa_sector: float = 32.0,
    ):
        self.kappa_product = float(kappa_product)
        self.kappa_family = float(kappa_family)
        self.kappa_sector = float(kappa_sector)
        self.global_stat = RunningGaussian()
        self.sector_stats: dict[str, RunningGaussian] = {}
        self.family_stats: dict[tuple[str, str], RunningGaussian] = {}
        self.product_stats: dict[tuple[str, str, str], RunningGaussian] = {}

    @staticmethod
    def _key(x: str | None) -> str:
        return (x or "").strip().lower()

    @staticmethod
    def _stat(store: dict, key):
        if key not in store:
            store[key] = RunningGaussian()
        return store[key]

    def update(
        self,
        price: float,
        sector: str,
        family: str = "",
        product: str = "",
        *,
        trusted: bool = False,
    ) -> None:
        if not trusted:
            return
        if not math.isfinite(price) or price <= 0:
            return
        lp = math.log(float(price))
        s, f, p = self._key(sector), self._key(family), self._key(product)
        self.global_stat.update(lp)
        self._stat(self.sector_stats, s).update(lp)
        if f:
            self._stat(self.family_stats, (s, f)).update(lp)
        if p:
            self._stat(self.product_stats, (s, f, p)).update(lp)

    @staticmethod
    def _blend(
        parent_mean: float,
        child: RunningGaussian | None,
        kappa: float,
    ) -> tuple[float, float]:
        if child is None or child.n == 0:
            return parent_mean, 0.0
        w = child.n / (child.n + kappa)
        return (1.0 - w) * parent_mean + w * child.mean, w

    def predict(
        self,
        sector: str,
        family: str = "",
        product: str = "",
    ) -> FairValueEstimate | None:
        if self.global_stat.n == 0:
            return None
        s, f, p = self._key(sector), self._key(family), self._key(product)
        mu = self.global_stat.mean
        effective_n = float(self.global_stat.n)
        weights = []

        sec = self.sector_stats.get(s)
        mu, w = self._blend(mu, sec, self.kappa_sector)
        if w:
            weights.append(w)
            effective_n = sec.n

        fam = self.family_stats.get((s, f)) if f else None
        mu, w = self._blend(mu, fam, self.kappa_family)
        if w:
            weights.append(w)
            effective_n = fam.n

        prod = self.product_stats.get((s, f, p)) if p else None
        mu, w = self._blend(mu, prod, self.kappa_product)
        if w:
            weights.append(w)
            effective_n = prod.n

        # Use the deepest available variance, with a conservative global floor.
        chosen = (
            prod
            if prod and prod.n >= 2
            else fam
            if fam and fam.n >= 2
            else sec
            if sec and sec.n >= 2
            else self.global_stat
        )
        var = max(float(chosen.variance), 0.0)
        floor = max(float(self.global_stat.variance), 0.0)
        log_sigma = math.sqrt(max(var, 0.25 * floor, 1e-6))
        depth = len(weights)
        sample_conf = effective_n / (effective_n + 12.0)
        confidence = max(
            0.0,
            min(1.0, sample_conf * (0.70 + 0.10 * depth)),
        )
        return FairValueEstimate(
            price=math.exp(mu),
            log_sigma=log_sigma,
            confidence=confidence,
            effective_n=effective_n,
        )
