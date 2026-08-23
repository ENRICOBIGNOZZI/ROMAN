from __future__ import annotations

import json
import math
import os
import re

from .entity import entity_key, match_confidence
from .feeds import reference_adapters
from .live import ShadowLiveEngine as _BaseShadowLiveEngine, _latest_rows
from .shadow_ledger import ShadowLedger
from .snapshot import SnapshotStore


_VIDEO_GAME_QUERIES = [
    "EarthBound Super Nintendo",
    "Chrono Trigger Super Nintendo",
    "Pokemon Emerald GameBoy Advance",
    "Zelda Ocarina of Time Nintendo 64",
    "Super Mario 64 Nintendo 64",
    "Pokemon Red GameBoy",
    "Nintendo Switch OLED",
    "PlayStation 5 Slim",
]

_VINYL_QUERIES = [
    "Pink Floyd Dark Side of the Moon vinyl",
    "The Beatles Abbey Road vinyl",
    "Daft Punk Discovery vinyl",
    "Nirvana Nevermind vinyl",
]

_TCG_QUERIES = [
    "Pokemon 151 booster box",
    "Pokemon Evolving Skies booster box",
    "Magic The Gathering booster box",
    "One Piece booster box",
]

_RICARDO_SEEDS = [
    "Rolex 124270",
    "Omega Speedmaster 310.30.42.50.01.001",
    "LEGO 75192",
    "LEGO 10307",
    "Pokemon Charizard PSA 10",
    "Pokemon 151 booster box",
    "Nike Jordan 1 Chicago",
    "Sony FE 24-70 GM II",
    "Nintendo Switch OLED",
    "iPhone 15 Pro 256GB",
    "RTX 4090",
    "Fender American Professional II Stratocaster",
]

_REFERENCE_QUERIES = {
    "cardmarket_public_reference": _TCG_QUERIES,
    "bricklink_reference": [
        "LEGO 75192",
        "LEGO 10307",
        "LEGO 10294",
        "LEGO 42143",
    ],
    "discogs_reference": _VINYL_QUERIES,
    "tcgapi_reference": _TCG_QUERIES,
    "pricecharting_reference": _VIDEO_GAME_QUERIES,
}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _weighted_median(rows: list[tuple[float, float]]) -> float | None:
    clean = sorted(
        (float(value), float(weight))
        for value, weight in rows
        if math.isfinite(float(value))
        and float(value) > 0
        and math.isfinite(float(weight))
        and float(weight) > 0
    )
    if not clean:
        return None
    total = sum(weight for _, weight in clean)
    running = 0.0
    for value, weight in clean:
        running += weight
        if running >= 0.5 * total:
            return value
    return clean[-1][0]


class ShadowLiveEngine(_BaseShadowLiveEngine):
    """Canonical production/shadow engine with trusted multi-source ingestion.

    The base live engine owns concrete market collection, scoring, FDR,
    allocation and ledger mechanics. This production boundary adds invariants:

    1. keep the exact scored candidate set that produced ledger marks;
    2. learn online only from positions the ledger actually closes against fresh
       executable evidence from the same exit route;
    3. expose expected net ROI separately from its lower-confidence bound;
    4. collect valuation-only APIs/downloads into a separate reference database;
    5. let reference data move fair value only through a bounded, uncertainty-
       aware update, never by creating an acquisition or exit route.
    """

    def __init__(self, *args, **kwargs):
        self.reference_snapshot_db = str(
            kwargs.pop("reference_snapshot_db", "data/roman_reference.sqlite")
        )
        super().__init__(*args, **kwargs)
        self._last_scored_candidates: list[dict] = []
        self.reference_adapters = reference_adapters()
        self.reference_feed_state: dict[str, dict] = {}
        self.reference_every_cycles = max(
            1, int(os.getenv("ROMAN_REFERENCE_EVERY_CYCLES", "12"))
        )
        self._reference_cycle_no = 0

        # The packed source catalog predates these new authorized feeds. Inject
        # explicit plans here so they are usable immediately without weakening
        # source policy or broadening every vertical indiscriminately.
        sector_names = [s.name for s in self.sectors.values()]
        self.plan["ricardo"] = list(dict.fromkeys(_RICARDO_SEEDS + sector_names))
        self.plan["pricecharting"] = list(_VIDEO_GAME_QUERIES)

        # eBay is the broadest cross-market bridge. Add high-identity vertical
        # seeds so videogame/vinyl/TCG reference markets can actually meet a
        # concrete listing on a common entity.
        ebay_plan = self.plan.get("ebay", [])
        self.plan["ebay"] = list(
            dict.fromkeys(
                _VIDEO_GAME_QUERIES
                + _VINYL_QUERIES
                + _TCG_QUERIES
                + ebay_plan
            )
        )[:800]

    def _sector(self, row):
        source = str(row.get("source") or "").lower()
        if source == "pricecharting":
            extra = row.get("extra") or {}
            genre = str(extra.get("genre") or "").lower()
            title = str(row.get("title") or "").lower()
            if genre == "systems" or any(
                token in title
                for token in (
                    "console",
                    "system",
                    "handheld",
                    "switch oled",
                    "playstation 5",
                    "ps5",
                    "xbox series",
                )
            ):
                sector = self.sectors.get("consoles")
            else:
                sector = self.sectors.get("retro_games")
            if sector is not None:
                return sector.key, sector.family
        return super()._sector(row)

    @staticmethod
    def _finite(value, default: float = 0.0) -> float:
        try:
            x = float(value)
            return x if math.isfinite(x) else float(default)
        except Exception:
            return float(default)

    @staticmethod
    def _reference_is_plausible(
        candidate: dict,
        reference: dict,
        match_score: float,
    ) -> bool:
        if match_score >= 0.94:
            return True

        # A shared seed query is useful but not sufficient by itself. Require both
        # titles to explain most of that seed and preserve all numeric identifiers.
        c_query = str(candidate.get("buy_query") or "").strip().lower()
        r_query = str((reference.get("extra") or {}).get("query") or "").strip().lower()
        if not c_query or c_query != r_query:
            return False
        q = _tokens(c_query)
        ct = _tokens(str(candidate.get("title") or ""))
        rt = _tokens(str(reference.get("title") or ""))
        if not q or not ct or not rt:
            return False
        q_nums = {x for x in q if any(ch.isdigit() for ch in x)}
        if q_nums and not (q_nums <= ct and q_nums <= rt):
            return False
        c_cover = len(q & ct) / len(q)
        r_cover = len(q & rt) / len(q)
        return c_cover >= 0.70 and r_cover >= 0.70

    def _reference_values(self, candidate: dict, references: list[dict], fx) -> list[dict]:
        base = self._finite(candidate.get("base_fair_value"), 0.0)
        if base <= 0:
            return []
        candidate_key = str(candidate.get("entity_key") or "")
        values: list[dict] = []
        for ref in references:
            extra = ref.get("extra") or {}
            if not bool(extra.get("reference_only")):
                continue
            ref_key = entity_key(ref)
            exact = bool(candidate_key and ref_key and candidate_key == ref_key)
            score = 1.0 if exact else float(match_confidence(candidate, ref))
            if not exact and not self._reference_is_plausible(candidate, ref, score):
                continue
            try:
                eur = fx.to_eur(
                    float(ref.get("price") or 0.0),
                    str(ref.get("currency") or ""),
                    False,
                )
            except Exception:
                eur = None
            if eur is None or eur <= 0 or not math.isfinite(float(eur)):
                continue
            ratio = float(eur) / base
            # Extreme disagreement is more likely mismatch/stale-condition data
            # than useful information. Preserve it in the DB but do not update FV.
            if ratio < 0.50 or ratio > 2.00:
                continue
            evidence_weight = 0.15 if exact else min(0.10, 0.03 + 0.07 * max(score - 0.70, 0.0) / 0.30)
            values.append(
                {
                    "value_eur": float(eur),
                    "evidence_weight": evidence_weight,
                    "source": str(ref.get("source") or "reference"),
                    "match_confidence": score,
                    "exact_entity": exact,
                    "observed_at": ref.get("observed_at"),
                }
            )
        values.sort(
            key=lambda x: (x["exact_entity"], x["match_confidence"], x["evidence_weight"]),
            reverse=True,
        )
        return values[:8]

    def _apply_reference_update(self, candidate: dict, references: list[dict], fx) -> None:
        evidence = self._reference_values(candidate, references, fx)
        candidate["reference_values"] = evidence
        if not evidence:
            candidate["predictive_confidence"] = candidate.get("ensemble_confidence", 0.0)
            return

        base = self._finite(candidate.get("base_fair_value"), 0.0)
        ref_fair = _weighted_median(
            [(x["value_eur"], x["evidence_weight"]) for x in evidence]
        )
        if base <= 0 or ref_fair is None:
            return

        weight = min(0.20, sum(float(x["evidence_weight"]) for x in evidence))
        market_base = base
        adjusted = (1.0 - weight) * market_base + weight * ref_fair
        gap = abs(ref_fair / market_base - 1.0)
        old_sigma = max(self._finite(candidate.get("model_sigma_roi"), 0.02), 0.0)
        disagreement_sigma = min(0.10, 0.50 * weight * gap)

        candidate["market_base_fair_value"] = market_base
        candidate["reference_fair_value"] = ref_fair
        candidate["reference_weight"] = weight
        candidate["base_fair_value"] = adjusted
        candidate["model_sigma_roi"] = math.sqrt(old_sigma**2 + disagreement_sigma**2)

        # Re-run the same unified model. The reference channel changes only its
        # fair-value prior + uncertainty; no separate vote or route is introduced.
        score = self.model.score(candidate)
        candidate.update(
            trade=score.trade,
            fair_value=score.fair_value,
            acquisition_cost=score.acquisition_cost,
            expected_exit_net=score.expected_exit_net,
            fair_value_net_roi=score.fair_value_net_roi,
            factor_net_roi=score.factor_net_roi,
            anomaly_net_roi=score.anomaly_net_roi,
            locked_net_roi=score.locked_net_roi,
            expected_holding_days=score.expected_holding_days,
            sale_prob_30d=score.sale_prob_30d,
            seller_success_prob=score.seller_success_prob,
            condition_risk=score.condition_risk,
            regime_weight=score.regime_weight,
            ensemble_confidence=score.ensemble_confidence,
            predictive_confidence=score.predictive_confidence,
            conservative_net_roi=score.conservative_net_roi,
            lcb_net_roi=score.lcb_net_roi,
            score_per_capital_day=score.score_per_capital_day,
            reason=score.reason,
        )

    def build_candidates(self):
        rows = super().build_candidates()
        references = _latest_rows(self.reference_snapshot_db, max_age_hours=24 * 8)
        fx = self.refresh_fx()
        for row in rows:
            self._apply_reference_update(row, references, fx)
            if row.get("predictive_confidence") is None:
                row["predictive_confidence"] = row.get("ensemble_confidence", 0.0)
        rows.sort(
            key=lambda x: self._finite(x.get("score_per_capital_day"), -1e9),
            reverse=True,
        )
        self._last_scored_candidates = rows
        return rows

    def collect_reference_cycle(self) -> dict[str, int]:
        """Collect authorized/public valuation feeds at a slower cadence.

        Rows are stored in a physically separate SQLite database. They are never
        read by the market collector and therefore cannot create a trade merely
        because a guide/statistic reports a high value.
        """
        should_collect = self._reference_cycle_no % self.reference_every_cycles == 0
        self._reference_cycle_no += 1
        if not should_collect:
            return {}

        store = SnapshotStore(self.reference_snapshot_db)
        counts: dict[str, int] = {}
        try:
            for source, adapter in self.reference_adapters.items():
                if not adapter.available():
                    self.reference_feed_state[source] = {
                        "status": "NO_CREDENTIALS",
                        "rows": 0,
                    }
                    continue
                total = 0
                error = ""
                queries = _REFERENCE_QUERIES.get(source, [])
                for query in queries[: max(1, min(self.queries_per_source, 2))]:
                    try:
                        rows = list(
                            adapter.fetch(query, limit=min(self.rows_per_query, 20))
                        )
                        store.append(rows)
                        total += len(rows)
                    except Exception as exc:
                        error = str(exc)[:240]
                counts[source] = total
                self.reference_feed_state[source] = {
                    "status": "OK"
                    if not error
                    else ("PARTIAL" if total else "ERROR"),
                    "rows": total,
                    "error": error,
                }
        finally:
            store.close()
        return counts

    def _event_exit_source(self, event: dict) -> str:
        explicit = str(event.get("exit_source") or "")
        if explicit:
            return explicit
        position_id = str(event.get("position_id") or "")
        if not position_id:
            return ""
        row = self.ledger.db.execute(
            """SELECT meta_json FROM shadow_marks
               WHERE position_id=? ORDER BY observed_at DESC LIMIT 1""",
            (position_id,),
        ).fetchone()
        if row is None:
            return ""
        try:
            meta = json.loads(row[0] or "{}")
        except Exception:
            return ""
        return str(meta.get("executable_exit_source") or "")

    def _matching_executable_candidate(self, event: dict) -> dict | None:
        entity = str(event.get("entity_key") or "")
        exit_source = self._event_exit_source(event)
        if not entity or not exit_source:
            return None
        target = self._finite(event.get("close_value"), -1.0)
        options: list[tuple[float, dict]] = []
        for candidate in self._last_scored_candidates:
            if str(candidate.get("entity_key") or "") != entity:
                continue
            if str(candidate.get("exit_source") or "") != exit_source:
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
                seller_route_key=str(candidate.get("seller_route_key") or "unknown"),
                sold=True,
                exposure_days=age_days,
                seller_success=None,
                realized_pnl_roi=self._finite(event.get("roi"), 0.0),
            )
            learned += 1
        return learned

    def dashboard_payload(self, candidates, basket):
        payload = super().dashboard_payload(candidates, basket)
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
            opportunity["lcb_roic"] = self._finite(candidate.get("lcb_net_roi"), -1.0)
            opportunity["confidence"] = self._finite(
                candidate.get(
                    "predictive_confidence",
                    candidate.get("ensemble_confidence", 0.0),
                ),
                0.0,
            )
            opportunity["reference_fair_value"] = candidate.get("reference_fair_value")
            opportunity["reference_weight"] = candidate.get("reference_weight", 0.0)

        status = dict(payload.get("model_status") or {})
        legacy = status.pop("Conservative ensemble", None)
        status["Unified predictive LCB"] = legacy or "ONLINE"
        payload["model_status"] = status
        payload["reference_feeds"] = [
            dict(source=key, **value)
            for key, value in sorted(self.reference_feed_state.items())
        ]
        return payload

    def run_cycle(self, fdr_alpha: float | None = None):
        # Refresh slow reference data first so a newly collected guide can affect
        # this cycle's bounded fair-value update. Failure is isolated per source.
        reference_counts = self.collect_reference_cycle()
        payload = super().run_cycle(fdr_alpha=fdr_alpha)
        learned = self._learn_closed_outcomes(
            list(payload.get("closed_this_cycle") or [])
        )
        diagnostics = dict(payload.get("diagnostics") or {})
        diagnostics["learned_closed_outcomes"] = learned
        diagnostics["reference_rows_this_cycle"] = sum(reference_counts.values())
        diagnostics["reference_cycle_counts"] = reference_counts
        payload["diagnostics"] = diagnostics
        payload["reference_feeds"] = [
            dict(source=key, **value)
            for key, value in sorted(self.reference_feed_state.items())
        ]

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
