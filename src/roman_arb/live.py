from __future__ import annotations

import json
import math
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from .allocator import CapitalDayAllocator
from .config import load_config
from .entity import entity_key, structured_codes
from .fdr import PosteriorFDRSelector
from .feeds import load_source_registry, official_adapters
from .fees import FeeEngine
from .fx import FXBook, refresh_ecb
from .model_stack import SimpleModelStack
from .scheduler import AdaptiveQueryScheduler
from .shadow_ledger import ShadowLedger
from .snapshot import SnapshotStore

_MERCADOLIBRE_MARKETS = {
    "mercadolibre_mx",
    "mercadolibre_ar",
    "mercadolibre_br",
    "mercadolibre_cl",
    "mercadolibre_co",
    "mercadolibre_uy",
}
_BROAD_MARKETS = {"ebay", "mercadolibre", "rakuten_ichiba"} | _MERCADOLIBRE_MARKETS

# High-identity diagnostic seeds. They are deliberately SKU/reference-heavy so
# the same economic object has a chance to be found on more than one market.
_SEED_LIVE_QUERIES = [
    "Rolex 124270",
    "Omega Speedmaster 310.30.42.50.01.001",
    "LEGO 75192",
    "LEGO 10307",
    "Pokemon Charizard PSA 10",
    "Pokemon 151 booster box",
    "Nike Jordan 1 Chicago",
    "Adidas Yeezy 350",
    "Sony FE 24-70 GM II",
    "Canon RF 70-200 F2.8",
    "Nintendo Switch OLED",
    "PlayStation 5 Slim",
    "iPhone 15 Pro 256GB",
    "Samsung S24 Ultra 256GB",
    "RTX 4090",
    "MacBook Pro M3 14 512GB",
    "Fender American Professional II Stratocaster",
    "Boss CE-2W",
]


def _now():
    return datetime.now(timezone.utc)


def _iso(dt=None):
    return (dt or _now()).isoformat()


def _parse_ts(x):
    try:
        d = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _weighted_median(values: list[tuple[float, float]]) -> float | None:
    clean = sorted(
        (float(v), max(0.0, float(w)))
        for v, w in values
        if v and v > 0 and w > 0
    )
    if not clean:
        return None
    total = sum(w for _, w in clean)
    acc = 0.0
    for value, weight in clean:
        acc += weight
        if acc >= 0.5 * total:
            return value
    return clean[-1][0]


def build_query_plan(config_path: str | None = None) -> dict[str, list[str]]:
    _, _, sectors = load_config(config_path)
    registry = set(load_source_registry()) | _MERCADOLIBRE_MARKETS
    names = [s.name for s in sectors.values()]
    plan: dict[str, list[str]] = {}
    for source in registry:
        if source in _BROAD_MARKETS:
            queries = _SEED_LIVE_QUERIES + names
        else:
            queries = [
                s.name for s in sectors.values() if source in set(s.source_venues)
            ]
        if queries:
            plan[source] = list(dict.fromkeys(q for q in queries if q))
    if len(plan) < 20:
        fallback = _SEED_LIVE_QUERIES[:4] + names[: max(1, min(8, len(names)))]
        for source in registry:
            plan.setdefault(source, fallback.copy())
            if len(plan) >= 20:
                break
    return plan


def _latest_rows(db_path: str, max_age_hours: float = 12.0):
    p = Path(db_path)
    if not p.exists():
        return []
    db = sqlite3.connect(p)
    db.row_factory = sqlite3.Row
    cutoff = (_now() - timedelta(hours=max_age_hours)).isoformat()
    q = """SELECT l.* FROM listings l JOIN (
      SELECT source,external_id,MAX(observed_at) observed_at FROM listings
      WHERE observed_at>=? GROUP BY source,external_id
    ) z ON l.source=z.source AND l.external_id=z.external_id
       AND l.observed_at=z.observed_at WHERE l.price>0"""
    rows = [dict(r) for r in db.execute(q, (cutoff,))]
    db.close()
    for r in rows:
        try:
            r["extra"] = json.loads(r.get("extra_json") or "{}")
        except Exception:
            r["extra"] = {}
    return rows


def _age_h(row):
    d = _parse_ts(row.get("observed_at", ""))
    return 1e9 if d is None else max(0.0, (_now() - d).total_seconds() / 3600)


def _freshness(row, half_life_h=6.0):
    return math.exp(
        -math.log(2.0) * _age_h(row) / max(half_life_h, 1e-6)
    )


def _group_key(row):
    k = entity_key(row)
    return k if k.startswith(("g:", "id:", "fp:")) else ""


class ShadowLiveEngine:
    """Paper-only live collector -> online models -> 10k path-dependent ledger."""

    def __init__(
        self,
        capital=10_000.0,
        snapshot_db="data/roman_snapshots.sqlite",
        tracking_db="data/roman_tracking.sqlite",
        shadow_db="data/roman_shadow.sqlite",
        dashboard_path="outputs/live/dashboard.json",
        fx_path="data/fx_rates.json",
        queries_per_source=2,
        rows_per_query=40,
    ):
        self.capital = float(capital)
        self.snapshot_db = snapshot_db
        self.tracking_db = tracking_db
        self.shadow_db = shadow_db
        self.dashboard_path = Path(dashboard_path)
        self.dashboard_path.parent.mkdir(parents=True, exist_ok=True)
        self.fx_path = fx_path
        self.queries_per_source = int(queries_per_source)
        self.rows_per_query = int(rows_per_query)
        self.assumptions, self.venues, self.sectors = load_config()
        self.fees = FeeEngine(self.venues)
        self.model = SimpleModelStack(
            min_lcb_roi=max(
                0.002, float(self.assumptions.get("min_lcb_roi", 0.003))
            ),
            lcb_z=max(1.0, float(self.assumptions.get("lcb_z", 1.28))),
        )
        self.allocator = CapitalDayAllocator(
            capital=self.capital,
            cash_buffer_fraction=float(
                self.assumptions.get("cash_buffer_fraction", 0.20)
            ),
        )
        self.ledger = ShadowLedger(self.shadow_db, capital=self.capital)
        self.plan = build_query_plan()
        self.adapters = official_adapters()
        self.started_at = _now()
        self.feed_state: dict[str, dict] = {}
        self._followup_codes: list[str] = []
        # Returns are formed within the same marketplace for a given entity. A
        # changing cross-market composition must not be mistaken for a price move.
        self._last_entity_source_price: dict[tuple[str, str], float] = {}
        self._return_history: list[dict[str, float]] = []
        self._pca_signal_by_entity: dict[str, object] = {}
        self._latest_entity_return: dict[str, float] = {}
        self._cycle_no = 0
        self._last_new_positions = 0

    def close(self):
        self.ledger.close()

    def refresh_fx(self):
        b = FXBook.load(self.fx_path)
        age = b.age_hours()
        if b.source == "missing" or age is None or age > 20:
            try:
                refresh_ecb(
                    self.fx_path,
                    friction_pct=float(
                        os.getenv("ROMAN_FX_FRICTION", "0.004")
                    ),
                )
                b = FXBook.load(self.fx_path)
            except Exception:
                pass
        return b

    def _inject_followups(self, rows) -> None:
        new_codes = []
        for r in rows:
            for code in structured_codes(r.title):
                if len(code) >= 5 and code not in self._followup_codes:
                    new_codes.append(code)
        if not new_codes:
            return
        self._followup_codes = (new_codes + self._followup_codes)[:160]
        for source in _BROAD_MARKETS:
            base = self.plan.get(source, [])
            self.plan[source] = list(
                dict.fromkeys(new_codes[:25] + base)
            )[:650]

    def collect_cycle(self):
        store = SnapshotStore(self.snapshot_db)
        sch = AdaptiveQueryScheduler(self.tracking_db)
        counts: dict[str, int] = {}
        all_rows = []
        try:
            for source, adapter in self.adapters.items():
                if not adapter.available():
                    self.feed_state[source] = {
                        "status": "NO_CREDENTIALS",
                        "rows": 0,
                        "last": _iso(),
                    }
                    continue
                queries = self.plan.get(source, [])
                chosen = sch.choose(source, queries, self.queries_per_source)
                total = 0
                err = ""
                for q in chosen:
                    try:
                        rows = list(
                            adapter.fetch(q, limit=self.rows_per_query)
                        )
                        for r in rows:
                            r.extra = dict(r.extra or {}, query=q)
                        store.append(rows)
                        sch.record_scan(source, q, len(rows))
                        total += len(rows)
                        all_rows.extend(rows)
                    except Exception as e:
                        err = str(e)[:240]
                        sch.record_error(source, q, err)
                counts[source] = total
                self.feed_state[source] = {
                    "status": "OK"
                    if not err
                    else ("PARTIAL" if total else "ERROR"),
                    "rows": total,
                    "last": _iso(),
                    "error": err,
                }
        finally:
            sch.close()
            store.close()
        self._inject_followups(all_rows)
        return counts

    def _sector(self, row):
        q = str((row.get("extra") or {}).get("query") or "").lower()
        title = str(row.get("title") or "").lower()
        best = (0, None)
        for s in self.sectors.values():
            n = s.name.lower()
            score = (
                3
                if q == n and q
                else 2
                if q and (q in n or n in q)
                else 1
                if s.family and s.family.lower() in title
                else 0
            )
            if score > best[0]:
                best = (score, s)
        if best[1]:
            return best[1].key, best[1].family

        aliases = [
            (("rolex", "omega", "cartier", "speedmaster", "seiko"), "modern_watches"),
            (("lego",), "lego_sealed"),
            (("pokemon", "psa", "bgs"), "tcg_graded"),
            (("jordan", "yeezy", "nike", "adidas"), "sneakers_ds"),
            (("canon", "sony fe", "nikon", "24-70", "70-200"), "camera_lenses"),
            (("iphone", "samsung s", "pixel"), "smartphones"),
            (("rtx", "radeon"), "gpus"),
            (("nintendo", "playstation", "xbox"), "consoles"),
            (("macbook", "ipad"), "laptops_tablets"),
            (("fender", "gibson", "boss "), "guitar_pedals"),
        ]
        text = f"{q} {title}"
        for words, key in aliases:
            if any(w in text for w in words) and key in self.sectors:
                s = self.sectors[key]
                return s.key, s.family
        return "unknown", ""

    def _prepare_groups(self, rows, fx):
        groups = defaultdict(list)
        for r in rows:
            k = _group_key(r)
            if not k:
                continue
            eur = fx.to_eur(
                float(r["price"]), str(r.get("currency") or ""), False
            )
            if eur and eur > 0:
                rr = dict(r, entity_key=k, price_eur=eur)
                groups[k].append(rr)
        return groups

    def _update_return_models(self, groups: dict[str, list[dict]]) -> None:
        current: dict[tuple[str, str], float] = {}
        entity_sector: dict[str, str] = {}
        entity_sources: dict[str, set[str]] = defaultdict(set)

        for k, rows in groups.items():
            by_source: dict[str, list[float]] = defaultdict(list)
            for r in rows:
                v = float(r.get("price_eur") or 0.0)
                if v > 0 and math.isfinite(v):
                    by_source[str(r.get("source") or "unknown")].append(v)
            for source, vals in by_source.items():
                current[(k, source)] = float(np.median(vals))
                entity_sources[k].add(source)
            sk, _ = self._sector(rows[0])
            entity_sector[k] = sk

        returns: dict[str, float] = {}
        sector_returns: dict[str, list[float]] = defaultdict(list)
        for k, sources in entity_sources.items():
            same_source_returns = []
            for source in sources:
                price = current.get((k, source))
                prev = self._last_entity_source_price.get((k, source))
                if not price or not prev or prev <= 0:
                    continue
                ret = math.log(price / prev)
                if math.isfinite(ret) and abs(ret) <= 0.40:
                    same_source_returns.append(ret)
            if not same_source_returns:
                continue
            ret = float(np.median(same_source_returns))
            returns[k] = ret
            sk = entity_sector.get(k, "unknown")
            if sk != "unknown":
                sector_returns[sk].append(ret)

        self._latest_entity_return = returns

        factor_updates = {}
        for sk, vals in sector_returns.items():
            med = float(np.median(vals))
            factor_updates[f"sector:{sk}"] = med
            self.model.regime.update(sk, med)
        if factor_updates:
            self.model.update_dynamic_factors(factor_updates)

        if returns:
            self._return_history.append(dict(returns))
            self._return_history = self._return_history[-180:]

        self._pca_signal_by_entity = {}
        if len(self._return_history) >= 12:
            coverage = Counter()
            for row in self._return_history:
                coverage.update(row.keys())
            min_obs = max(6, len(self._return_history) // 3)
            names = [
                k for k, n in coverage.most_common(40) if n >= min_obs
            ]
            if len(names) >= 4:
                x = np.full(
                    (len(self._return_history), len(names)), np.nan
                )
                idx = {n: j for j, n in enumerate(names)}
                for i, row in enumerate(self._return_history):
                    for key, value in row.items():
                        if key in idx:
                            x[i, idx[key]] = float(value)
                fit = self.model.fit_pca(x, names)
                if fit is not None:
                    sigs = self.model.factor_signals(returns)
                    self._pca_signal_by_entity = {
                        s.name: s for s in sigs
                    }

        self._last_entity_source_price = current

    def build_candidates(self):
        rows = _latest_rows(self.snapshot_db, 12)
        fx = self.refresh_fx()
        groups = self._prepare_groups(rows, fx)
        self._update_return_models(groups)
        out = []

        for k, g in groups.items():
            if len({r["source"] for r in g}) < 2 and not any(
                (r.get("extra") or {}).get("highest_bid") for r in g
            ):
                continue
            for buy in g:
                sk, fam = self._sector(buy)
                s = self.sectors.get(sk)
                if s is None:
                    continue
                buy_eur = fx.acquisition_eur(
                    float(buy["price"]),
                    str(buy.get("currency") or ""),
                )
                if not buy_eur:
                    continue

                comps = []
                fair_observations: list[tuple[float, float]] = []
                best = None
                best_conservative_net = -1e18
                buy_site = str(
                    (buy.get("extra") or {}).get("site_id") or ""
                )

                for comp in g:
                    if (
                        comp["source"] == buy["source"]
                        and comp["external_id"] == buy["external_id"]
                    ):
                        continue
                    src = str(comp["source"])
                    gross = float(comp["price_eur"])
                    v = self.venues.get(src)
                    fee = float(v.sell_fee) if v else 0.13
                    fixed = float(v.fixed_exit) if v else 0.0
                    vh = float(v.price_haircut) if v else 0.0
                    comp_site = str(
                        (comp.get("extra") or {}).get("site_id") or ""
                    )
                    cross_border = bool(
                        buy_site and comp_site and buy_site != comp_site
                    )

                    gross_mark = gross * (1.0 - vh) * 0.95
                    shipping = 0.0
                    if cross_border:
                        gross_mark *= 0.90
                        shipping = max(18.0, 0.015 * gross_mark)

                    # ``price_eur`` is an ECB-mid valuation. Actual conversion of
                    # foreign exit proceeds must pay the same explicit FX friction
                    # used elsewhere in the live engine.
                    comp_currency = str(comp.get("currency") or "").upper()
                    exit_fx_mult = (
                        1.0 - fx.friction_pct
                        if comp_currency and comp_currency != "EUR"
                        else 1.0
                    )
                    net = (
                        gross_mark * exit_fx_mult * (1.0 - fee)
                        - fixed
                        - shipping
                    )
                    fr = _freshness(comp)
                    exec_conf = fr * (0.18 if cross_border else 0.32)
                    comps.append(
                        {
                            "net_value": net,
                            "freshness": fr,
                            "executable_confidence": exec_conf,
                            "source": src,
                            "currency": comp_currency,
                            "cross_border": cross_border,
                        }
                    )
                    fair_observations.append(
                        (gross_mark, max(0.03, exec_conf))
                    )
                    conservative_net = net - 0.03 * gross_mark * (
                        1.0 - exec_conf
                    )
                    if conservative_net > best_conservative_net:
                        best_conservative_net = conservative_net
                        best = (
                            src,
                            gross_mark,
                            fee,
                            fixed,
                            shipping,
                            cross_border,
                        )

                locked = None
                for comp in g:
                    hb = (comp.get("extra") or {}).get("highest_bid")
                    if hb in (None, "", 0, "0") or _age_h(comp) > 1.5:
                        continue
                    b = fx.to_eur(
                        float(hb),
                        str(comp.get("currency") or ""),
                        True,
                    )
                    if b and (locked is None or b > locked[0]):
                        locked = (b, str(comp["source"]))

                if best is None and locked is None:
                    continue

                robust_fair = _weighted_median(fair_observations)
                if robust_fair is None and locked is not None:
                    robust_fair = float(locked[0])
                if robust_fair is None or robust_fair <= 0:
                    continue

                planned_exit_price = 0.0
                if best is not None:
                    (
                        exit_src,
                        planned_exit_price,
                        exit_fee,
                        exit_fixed,
                        exit_shipping,
                        cross_border,
                    ) = best
                else:
                    exit_src = locked[1]
                    v = self.venues.get(exit_src)
                    exit_fee = float(v.sell_fee) if v else 0.13
                    exit_fixed = float(v.fixed_exit) if v else 0.0
                    exit_shipping = 0.0
                    cross_border = False

                acq = buy_eur * (1.0 + s.buy_cost_pct) + s.buy_fixed
                problem = acq * s.problem_prob * s.problem_loss
                c = {
                    "entity_key": k,
                    "sector": s.key,
                    "family": fam,
                    "product": k,
                    "title": buy.get("title", ""),
                    # Real marketplace condition text must reach the condition model.
                    "description": str(buy.get("condition") or ""),
                    "buy_source": buy["source"],
                    "buy_external_id": buy["external_id"],
                    "buy_url": buy.get("url", ""),
                    "buy_price": buy_eur,
                    "buy_fee_rate": s.buy_cost_pct,
                    "buy_fixed": s.buy_fixed,
                    "base_fair_value": float(robust_fair),
                    "planned_exit_price": float(planned_exit_price or robust_fair),
                    "exit_source": exit_src,
                    "exit_fee_rate": float(exit_fee),
                    "exit_fixed": float(exit_fixed),
                    "exit_shipping": float(exit_shipping),
                    "expected_fraud_loss": float(problem),
                    "model_sigma_roi": max(0.018, float(s.model_sigma)),
                    "seller_route_key": (
                        f"{buy['source']}:{buy.get('seller', '')}->{exit_src}"
                    ),
                    "comparables_net": comps,
                    "buy_query": str(
                        (buy.get("extra") or {}).get("query") or ""
                    ),
                    "cross_border": bool(cross_border),
                }

                if locked:
                    v = self.venues.get(locked[1])
                    c.update(
                        locked_exit_bid=float(locked[0]),
                        exit_source=locked[1],
                        exit_fee_rate=float(v.sell_fee) if v else 0.13,
                        exit_fixed=float(v.fixed_exit) if v else 0.0,
                        exit_shipping=0.0,
                        locked=True,
                    )

                pca_sig = self._pca_signal_by_entity.get(k)
                if pca_sig is not None:
                    c["factor_residual_z"] = float(pca_sig.residual_z)
                    c["factor_confidence"] = float(pca_sig.confidence)
                elif k in self._latest_entity_return:
                    c["factor_loadings"] = {f"sector:{s.key}": 1.0}
                    c["item_return"] = float(
                        self._latest_entity_return[k]
                    )
                    c["factor_residual_scale"] = 0.025

                sc = self.model.score(c)
                row = dict(c)
                row.update(
                    trade=sc.trade,
                    fair_value=sc.fair_value,
                    acquisition_cost=sc.acquisition_cost,
                    expected_exit_net=sc.expected_exit_net,
                    fair_value_net_roi=sc.fair_value_net_roi,
                    factor_net_roi=sc.factor_net_roi,
                    anomaly_net_roi=sc.anomaly_net_roi,
                    locked_net_roi=sc.locked_net_roi,
                    expected_holding_days=sc.expected_holding_days,
                    sale_prob_30d=sc.sale_prob_30d,
                    seller_success_prob=sc.seller_success_prob,
                    condition_risk=sc.condition_risk,
                    regime_weight=sc.regime_weight,
                    ensemble_confidence=sc.ensemble_confidence,
                    conservative_net_roi=sc.conservative_net_roi,
                    lcb_net_roi=sc.lcb_net_roi,
                    score_per_capital_day=sc.score_per_capital_day,
                    reason=sc.reason,
                )
                out.append(row)

        out.sort(
            key=lambda x: float(x.get("score_per_capital_day", -1e9)),
            reverse=True,
        )
        return out

    def _record_scheduler_candidates(self, candidates: list[dict]) -> str:
        sch = None
        try:
            sch = AdaptiveQueryScheduler(self.tracking_db)
            sch.record_candidates(candidates)
            return ""
        except Exception as exc:
            return str(exc)[:500]
        finally:
            if sch is not None:
                try:
                    sch.close()
                except Exception:
                    pass

    def allocate(self, candidates):
        existing = self.ledger.open_positions()
        result = self.allocator.allocate(
            [c for c in candidates if c.get("trade")], existing=existing
        )
        self._last_new_positions = self.ledger.open_selected(
            list(result.selected)
        )
        self.ledger.mark(candidates)
        return self.ledger.open_positions()

    def record_cycle(
        self,
        rows: dict,
        candidates: list[dict],
        fdr_selected: int,
    ) -> None:
        reasons = Counter(
            str(c.get("reason") or "unknown") for c in candidates
        )
        self.ledger.log_cycle(
            rows=rows,
            raw_candidates=len(candidates),
            pre_fdr=sum(
                1 for c in candidates if c.get("pre_fdr_trade")
            ),
            fdr_selected=int(fdr_selected),
            new_positions=self._last_new_positions,
            reasons=dict(reasons),
        )
        self._cycle_no += 1

    def dashboard_payload(self, candidates, basket):
        s = self.ledger.summary()
        elapsed = (_now() - self.started_at).total_seconds() / 3600
        ops = [
            {
                "entity": c.get("title") or c.get("entity_key"),
                "buy_source": c.get("buy_source"),
                "exit_source": c.get("exit_source"),
                "cost": c.get("acquisition_cost"),
                "net_edge": c.get("conservative_net_roi"),
                "lcb_roic": c.get("lcb_net_roi"),
                "expected_days": c.get("expected_holding_days"),
                "score_day": c.get("score_per_capital_day"),
                "confidence": c.get("ensemble_confidence"),
                "qualified": bool(c.get("trade")),
                "url": c.get("buy_url", ""),
                "reason": c.get("reason", ""),
                "cross_border": bool(c.get("cross_border")),
            }
            for c in candidates[:40]
        ]
        pca_online = self.model.pca.fit_ is not None
        kalman_online = any(
            f.state.initialized
            for f in self.model.dynamic_factors.filters.values()
        )
        regime_online = any(
            st.n >= 2 for st in self.model.regime.states.values()
        )
        return {
            "brand": "Reselling BOT",
            "status": "SHADOW-LIVE"
            if any(
                v.get("status") == "OK"
                for v in self.feed_state.values()
            )
            else "PRE-SHADOW",
            "updated_at": _iso(),
            "capital": self.capital,
            "nav": s.nav_mark,
            "net_pnl": s.mark_pnl,
            "mark_pnl": s.mark_pnl,
            "executable_pnl": s.executable_pnl,
            "cash": s.cash,
            "deployed": s.deployed_cost,
            "open_positions": s.open_positions,
            "locked_positions": s.locked_positions,
            "raw_signals": len(candidates),
            "qualified_signals": sum(
                1 for c in candidates if c.get("trade")
            ),
            "avg_net_roic": (
                s.executable_pnl / s.deployed_cost
                if s.deployed_cost > 0 and s.locked_positions > 0
                else None
            ),
            "experiment": {
                "label": "2H DIAGNOSTIC SHADOW",
                "elapsed_hours": elapsed,
                "target_hours": 2,
            },
            "nav_series": self.ledger.nav_series(1000),
            "opportunities": ops,
            "feeds": [
                dict(source=k, **v)
                for k, v in sorted(self.feed_state.items())
            ],
            "model_status": {
                "Hierarchical fair value": "ONLINE"
                if self.model.hierarchy.global_stat.n > 0
                else "WARMUP",
                "PCA residual factors": "ONLINE"
                if pca_online
                else "WARMUP",
                "Dynamic Kalman factors": "ONLINE"
                if kalman_online
                else "WARMUP",
                "Sale hazard / liquidity": "PRIOR+ONLINE",
                "Seller-quality posterior": "PRIOR",
                "Text + image condition risk": "TEXT_ONLY",
                "Regime detector": "ONLINE"
                if regime_online
                else "WARMUP",
                "Cross-market anomaly": "ONLINE",
                "Conservative ensemble": "ONLINE",
            },
            "diagnostics": {
                "cycle": self._cycle_no,
                "followup_codes": len(self._followup_codes),
                "pca_history_rows": len(self._return_history),
                "pca_rank": self.model.pca.fit_.rank if pca_online else 0,
                "latest_entity_returns": len(self._latest_entity_return),
            },
        }

    def run_cycle(self, fdr_alpha: float | None = None):
        """Run the same economic pipeline used by the long-lived daemon."""
        counts = self.collect_cycle()
        candidates = self.build_candidates()
        fdr = PosteriorFDRSelector(
            float(
                fdr_alpha
                if fdr_alpha is not None
                else os.getenv("ROMAN_FDR_ALPHA", "0.25")
            )
        )
        fdr_result = fdr.annotate(candidates)
        for c in candidates:
            c["pre_fdr_trade"] = bool(c.get("trade"))
            c["trade"] = bool(c.get("fdr_selected"))

        scheduler_error = self._record_scheduler_candidates(candidates)
        self.ledger.mark(candidates)
        closed = self.ledger.apply_exit_policy()
        basket = self.allocate(candidates)
        self.record_cycle(counts, candidates, len(fdr_result.selected))

        p = self.dashboard_payload(candidates, basket)
        summary = self.ledger.summary()
        p["cycle_rows"] = counts
        p["closed_this_cycle"] = closed
        p["realized_pnl"] = summary.realized_pnl
        p["aged_capital"] = summary.aged_capital
        p["scheduler_error"] = scheduler_error
        p["posterior_fdr"] = {
            "alpha": fdr_result.alpha,
            "mean_false_probability": fdr_result.mean_false_probability,
            "selected": len(fdr_result.selected),
        }
        self.dashboard_path.write_text(
            json.dumps(p, indent=2, ensure_ascii=False)
        )
        return p
