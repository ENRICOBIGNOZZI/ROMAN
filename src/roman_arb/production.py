from __future__ import annotations

import json
import math
import os

from .feeds import reference_adapters
from .live import ShadowLiveEngine as _BaseShadowLiveEngine
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
    "bricklink_reference": [
        "LEGO 75192",
        "LEGO 10307",
        "LEGO 10294",
        "LEGO 42143",
    ],
    "discogs_reference": [
        "Pink Floyd Dark Side of the Moon vinyl",
        "The Beatles Abbey Road vinyl",
        "Daft Punk Discovery vinyl",
        "Nirvana Nevermind vinyl",
    ],
    "tcgapi_reference": [
        "Pokemon 151 booster box",
        "Pokemon Evolving Skies booster box",
        "Magic The Gathering booster box",
        "One Piece booster box",
    ],
    "pricecharting_reference": _VIDEO_GAME_QUERIES,
}


class ShadowLiveEngine(_BaseShadowLiveEngine):
    """Canonical production/shadow engine with trusted multi-source ingestion.

    The base live engine owns concrete market collection, scoring, FDR,
    allocation and ledger mechanics. This production boundary adds invariants:

    1. keep the exact scored candidate set that produced ledger marks;
    2. learn online only from positions the ledger actually closes against fresh
       executable evidence from the same exit route;
    3. expose expected net ROI separately from its lower-confidence bound;
    4. collect valuation-only APIs into a separate reference database so they can
       never accidentally become acquisition or exit routes.
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

    def collect_reference_cycle(self) -> dict[str, int]:
        """Collect authorized valuation feeds at a slower cadence.

        Rows are stored in a physically separate SQLite database. They are not
        read by ``build_candidates`` and therefore cannot create a trade merely
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

    @staticmethod
    def _finite(value, default: float = 0.0) -> float:
        try:
            x = float(value)
            return x if math.isfinite(x) else float(default)
        except Exception:
            return float(default)

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
        payload["reference_feeds"] = [
            dict(source=key, **value)
            for key, value in sorted(self.reference_feed_state.items())
        ]
        return payload

    def run_cycle(self, fdr_alpha: float | None = None):
        payload = super().run_cycle(fdr_alpha=fdr_alpha)
        reference_counts = self.collect_reference_cycle()
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
