from __future__ import annotations

from .config import load_config
from .feeds import load_source_registry


_BROAD_MARKETS = {"ebay", "mercadolibre", "rakuten_ichiba"}


def build_query_plan(config_path: str | None = None) -> dict[str, list[str]]:
    """Build a deterministic source->query plan from the maximal catalog.

    Broad marketplaces receive the full sector universe. Specialist sources only
    receive sectors that explicitly name them as source venues.  Registry-only
    sources are still represented when the catalog maps at least one sector to
    them; this is useful for CSV/partner-feed ingestion even when there is no
    official API adapter.
    """
    _, _, sectors = load_config(config_path)
    registry = load_source_registry()
    names = [s.name for s in sectors.values()]
    plan: dict[str, list[str]] = {}

    for source in registry:
        queries: list[str] = []
        if source in _BROAD_MARKETS:
            queries = names.copy()
        else:
            for s in sectors.values():
                if source in set(s.source_venues):
                    queries.append(s.name)
        if queries:
            # Stable de-duplication while preserving catalog order.
            plan[source] = list(dict.fromkeys(q for q in queries if q))

    # Keep the registry auditable even if a catalog revision temporarily maps too
    # few specialist sources.  These fallback entries are planning metadata only;
    # the runtime still requires an authorized adapter or CSV feed to fetch them.
    if len(plan) < 20:
        fallback = names[: max(1, min(8, len(names)))]
        for source in registry:
            plan.setdefault(source, fallback.copy())
            if len(plan) >= 20:
                break
    return plan
