from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping

from .pure_arbitrage import ArbitrageLeg, PureArbitrageEngine, PureArbitrageOpportunity


def _f(row: Mapping, key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default) or default)
    except Exception:
        return float(default)


def build_executable_books(rows: Iterable[Mapping]) -> dict[str, dict[str, list[ArbitrageLeg]]]:
    """Convert normalized live rows into pure-arbitrage books.

    Required row fields:
      - entity_key
      - source (venue)

    A buy leg is emitted only if `executable_ask > 0`.
    A sell leg is emitted only if `executable_bid > 0`.

    This is intentional: ordinary listing `price` is *not* treated as an
    executable exit bid, preventing observed cross-market dispersion from being
    mislabeled as pure arbitrage.
    """
    books: dict[str, dict[str, list[ArbitrageLeg]]] = defaultdict(lambda: {"buys": [], "sells": []})

    for row in rows:
        entity = str(row.get("entity_key") or "").strip()
        venue = str(row.get("source") or row.get("venue") or "").strip()
        if not entity or not venue:
            continue

        qty = max(_f(row, "available_qty", 1.0), 1e-9)
        fill = max(0.0, min(1.0, _f(row, "fill_prob", 1.0)))
        latency = max(0.0, _f(row, "latency_ms", 0.0))
        stale = max(0.0, _f(row, "stale_ms", 0.0))
        route_risk = max(0.0, min(1.0, _f(row, "route_risk", 0.0)))

        ask = _f(row, "executable_ask", 0.0)
        if ask > 0:
            books[entity]["buys"].append(
                ArbitrageLeg(
                    venue=venue,
                    side="buy",
                    executable_price=ask,
                    fee_rate=_f(row, "buy_fee_rate", 0.0),
                    fixed_fee=_f(row, "buy_fixed", 0.0),
                    shipping=_f(row, "buy_shipping", 0.0),
                    tax=_f(row, "buy_tax", 0.0),
                    authentication=_f(row, "buy_authentication_cost", 0.0),
                    fx_cost=_f(row, "buy_fx_cost", 0.0),
                    other_cost=_f(row, "buy_other_cost", 0.0),
                    available_qty=qty,
                    fill_prob=fill,
                    latency_ms=latency,
                    stale_ms=stale,
                    route_risk=route_risk,
                )
            )

        bid = _f(row, "executable_bid", 0.0)
        if bid > 0:
            books[entity]["sells"].append(
                ArbitrageLeg(
                    venue=venue,
                    side="sell",
                    executable_price=bid,
                    fee_rate=_f(row, "sell_fee_rate", row.get("exit_fee_rate", 0.0)),
                    fixed_fee=_f(row, "sell_fixed", row.get("exit_fixed", 0.0)),
                    shipping=_f(row, "sell_shipping", row.get("exit_shipping", 0.0)),
                    tax=_f(row, "sell_tax", row.get("exit_tax", 0.0)),
                    authentication=_f(row, "sell_authentication_cost", row.get("authentication_cost", 0.0)),
                    fx_cost=_f(row, "sell_fx_cost", row.get("fx_cost", 0.0)),
                    other_cost=(
                        _f(row, "sell_other_cost", 0.0)
                        + _f(row, "expected_return_loss", 0.0)
                        + _f(row, "expected_fraud_loss", 0.0)
                    ),
                    available_qty=qty,
                    fill_prob=fill,
                    latency_ms=latency,
                    stale_ms=stale,
                    route_risk=route_risk,
                )
            )

    return dict(books)


def scan_executable_rows(
    rows: Iterable[Mapping],
    engine: PureArbitrageEngine | None = None,
) -> list[PureArbitrageOpportunity]:
    engine = engine or PureArbitrageEngine()
    return engine.scan_market(build_executable_books(rows))
