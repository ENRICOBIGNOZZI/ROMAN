from __future__ import annotations

import json
import math

from .live import ShadowLiveEngine as _BaseShadowLiveEngine
from .shadow_ledger import ShadowLedger


class ShadowLiveEngine(_BaseShadowLiveEngine):
    """Canonical production/shadow engine with a closed-outcome feedback loop.

    The base live engine owns collection, scoring, FDR, allocation and ledger
    mechanics. This production boundary adds the invariants that must remain true
    in the deployed path:

    1. keep the exact scored candidate set that produced ledger marks;
    2. learn online only from positions the ledger actually closes against fresh
       executable evidence;
    3. expose expected net ROI separately from its lower-confidence bound.

    Current asks, model marks and repeated locked quotes never become persistent
    fair-value observations merely because they were seen.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_scored_candidates: list[dict] = []

    def build_candidates(self):
        rows = super().build_candidates()
        for row in rows:
            # New semantic name used by the FDR gate; keep the old field for
            # dashboard/storage compatibility while downstream code migrates.
            if row.get("predictive_confidence") is None:
                row["predictive_confidence"] = row.get(
                    "ensemble_confidence", 0.0
                )
        self._last_scored_candidates = rows
        return rows

    @staticmethod
    def _finite(value, default: float = 0.0) -> float:
        try:
            x = float(value)
            return x if math.isfinite(x) else float(default)
        except Exception:
            return float(default)

    def _matching_executable_candidate(self, event: dict) -> dict | None:
        entity = str(event.get("entity_key") or "")
        if not entity:
            return None
        target = self._finite(event.get("close_value"), -1.0)
        options: list[tuple[float, dict]] = []
        for candidate in self._last_scored_candidates:
            if str(candidate.get("entity_key") or "") != entity:
                continue
            if not bool(candidate.get("locked")):
                continue
            gross_bid = self._finite(candidate.get("locked_exit_bid"), 0.0)
            if gross_bid <= 0:
                continue
            executable = ShadowLedger._candidate_executable_value(candidate)
            if executable is None or executable <= 0:
                continue
            distance = abs(float(executable) - target) if target > 0 else 0.0
            options.append((distance, candidate))
        if not options:
            return None
        options.sort(key=lambda x: x[0])
        return options[0][1]

    def _learn_closed_outcomes(self, closed: list[dict]) -> int:
        learned = 0
        for event in closed:
            candidate = self._matching_executable_candidate(event)
            if candidate is None:
                # Fail closed: without the exact executable route that generated
                # the paper close, do not manufacture a training observation.
                continue
            gross_exit = self._finite(candidate.get("locked_exit_bid"), 0.0)
            if gross_exit <= 0:
                continue
            sector = str(candidate.get("sector") or "unknown")
            family = str(candidate.get("family") or "")
            entity = str(candidate.get("entity_key") or "")
            age_days = max(self._finite(event.get("age_days"), 0.0), 1e-6)
            self.model.observe_execution(
                exit_price=gross_exit,
                sector=sector,
                family=family,
                product=entity,
                seller_route_key=str(
                    candidate.get("seller_route_key") or "unknown"
                ),
                sold=True,
                exposure_days=age_days,
                # Shadow P&L is an economic outcome, not evidence that the seller
                # was good/bad. Seller labels require a separate explicit event.
                seller_success=None,
                realized_pnl_roi=self._finite(event.get("roi"), 0.0),
            )
            learned += 1
        return learned

    def dashboard_payload(self, candidates, basket):
        payload = super().dashboard_payload(candidates, basket)

        # The base dashboard historically called the conservative LCB `net_edge`.
        # Production telemetry must distinguish the predictive mean from its risk
        # bound. The base opportunity list follows candidates[:40] in the same
        # order, so no fuzzy entity lookup is needed here.
        for opportunity, candidate in zip(
            payload.get("opportunities") or [], candidates[:40]
        ):
            cost = self._finite(candidate.get("acquisition_cost"), 0.0)
            expected_exit = self._finite(candidate.get("expected_exit_net"), 0.0)
            expected_roi = (
                (expected_exit - cost) / cost
                if cost > 0 and expected_exit > 0
                else 0.0
            )
            opportunity["net_edge"] = expected_roi
            opportunity["expected_net_roi"] = expected_roi
            opportunity["lcb_roic"] = self._finite(
                candidate.get("lcb_net_roi"), -1.0
            )
            opportunity["confidence"] = self._finite(
                candidate.get(
                    "predictive_confidence",
                    candidate.get("ensemble_confidence", 0.0),
                ),
                0.0,
            )

        status = dict(payload.get("model_status") or {})
        legacy = status.pop("Conservative ensemble", None)
        status["Unified predictive LCB"] = legacy or "ONLINE"
        payload["model_status"] = status
        return payload

    def run_cycle(self, fdr_alpha: float | None = None):
        payload = super().run_cycle(fdr_alpha=fdr_alpha)
        learned = self._learn_closed_outcomes(
            list(payload.get("closed_this_cycle") or [])
        )
        diagnostics = dict(payload.get("diagnostics") or {})
        diagnostics["learned_closed_outcomes"] = learned
        payload["diagnostics"] = diagnostics

        # Learning happens after the close event, so refresh the model status and
        # persist the final telemetry for this cycle.
        status = dict(payload.get("model_status") or {})
        status["Hierarchical fair value"] = (
            "ONLINE"
            if self.model.hierarchy.global_stat.n > 0
            else "WARMUP"
        )
        payload["model_status"] = status
        self.dashboard_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False)
        )
        return payload
