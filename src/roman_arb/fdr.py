from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class FDRResult:
    selected: tuple[str, ...]
    mean_false_probability: float
    alpha: float


def _finite(x, default: float = 0.0) -> float:
    try:
        v = float(x)
        return v if math.isfinite(v) else float(default)
    except Exception:
        return float(default)


def _entity_key(c: dict) -> str:
    return str(c.get("entity_key") or c.get("buy_external_id") or id(c))


def _candidate_key(c: dict) -> str:
    """Stable route-level key; one economic entity can have several routes."""
    return "|".join(
        (
            _entity_key(c),
            str(c.get("buy_source") or ""),
            str(c.get("buy_external_id") or ""),
            str(c.get("exit_source") or ""),
        )
    )


class PosteriorFDRSelector:
    """Provisional confidence-budget gate for the wide universe.

    ``ensemble_confidence`` is *not* yet a calibrated posterior probability. Until
    forward outcomes are available, this class is deliberately only a conservative
    ranking/selection gate, not a claim of exact frequentist FDR control.

    The selector first keeps one economically best route per entity (maximum net
    LCB profit per capital-day), then selects the largest confidence-ranked prefix
    whose mean local false score ``1-confidence`` does not exceed ``alpha``. Only
    the exact selected route is annotated. This prevents confidence from one route
    leaking to every candidate that shares the same entity key.
    """

    def __init__(self, alpha: float = 0.25):
        self.alpha = max(0.0, min(1.0, float(alpha)))

    def _best_route_per_entity(self, candidates: list[dict]) -> list[dict]:
        best: dict[str, dict] = {}
        for c in candidates:
            if not c.get("trade"):
                continue
            entity = _entity_key(c)
            prev = best.get(entity)
            if prev is None:
                best[entity] = c
                continue
            # Economic route choice first; confidence is a tie-breaker only.
            cur_rank = (
                _finite(c.get("score_per_capital_day"), -1e9),
                _finite(c.get("lcb_net_roi"), -1e9),
                _finite(c.get("ensemble_confidence"), 0.0),
            )
            prev_rank = (
                _finite(prev.get("score_per_capital_day"), -1e9),
                _finite(prev.get("lcb_net_roi"), -1e9),
                _finite(prev.get("ensemble_confidence"), 0.0),
            )
            if cur_rank > prev_rank:
                best[entity] = c
        return list(best.values())

    def select(self, candidates: list[dict]) -> FDRResult:
        rows = []
        for c in self._best_route_per_entity(candidates):
            conf = max(
                0.0,
                min(1.0, _finite(c.get("ensemble_confidence"), 0.0)),
            )
            local_false = 1.0 - conf
            rows.append((local_false, _candidate_key(c), c))

        rows.sort(
            key=lambda x: (
                x[0],
                -_finite(x[2].get("score_per_capital_day"), -1e9),
            )
        )
        chosen: list[str] = []
        running = 0.0
        for lf, key, _ in rows:
            new_mean = (running + lf) / (len(chosen) + 1)
            if new_mean <= self.alpha:
                chosen.append(key)
                running += lf
            else:
                break
        mean = running / len(chosen) if chosen else 0.0
        return FDRResult(tuple(chosen), mean, self.alpha)

    def annotate(self, candidates: list[dict]) -> FDRResult:
        result = self.select(candidates)
        selected = set(result.selected)
        for c in candidates:
            exact_key = _candidate_key(c)
            c["fdr_selected"] = bool(c.get("trade") and exact_key in selected)
            if c.get("trade") and not c["fdr_selected"]:
                c["reason"] = str(c.get("reason") or "") + "|posterior_fdr_gate"
        return result
