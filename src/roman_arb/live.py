from __future__ import annotations

import json
import math
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .allocator import CapitalDayAllocator
from .config import load_config
from .entity import entity_key
from .feeds import load_source_registry, official_adapters
from .fees import FeeEngine
from .fx import FXBook, refresh_ecb
from .model_stack import SimpleModelStack
from .scheduler import AdaptiveQueryScheduler
from .snapshot import SnapshotStore

_BROAD_MARKETS = {"ebay", "mercadolibre", "rakuten_ichiba"}


def _now(): return datetime.now(timezone.utc)
def _iso(dt=None): return (dt or _now()).isoformat()

def _parse_ts(x):
    try:
        d=datetime.fromisoformat(str(x).replace("Z","+00:00")); return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception: return None


def build_query_plan(config_path: str | None = None) -> dict[str, list[str]]:
    _, _, sectors = load_config(config_path); registry=load_source_registry(); names=[s.name for s in sectors.values()]
    plan={}
    for source in registry:
        if source in _BROAD_MARKETS: queries=names.copy()
        else: queries=[s.name for s in sectors.values() if source in set(s.source_venues)]
        if queries: plan[source]=list(dict.fromkeys(q for q in queries if q))
    if len(plan)<20:
        fallback=names[:max(1,min(8,len(names)))]
        for source in registry:
            plan.setdefault(source,fallback.copy())
            if len(plan)>=20: break
    return plan


def _latest_rows(db_path: str, max_age_hours: float=12.0):
    p=Path(db_path)
    if not p.exists(): return []
    db=sqlite3.connect(p); db.row_factory=sqlite3.Row
    cutoff=(_now()-timedelta(hours=max_age_hours)).isoformat()
    q="""SELECT l.* FROM listings l JOIN (
      SELECT source,external_id,MAX(observed_at) observed_at FROM listings
      WHERE observed_at>=? GROUP BY source,external_id
    ) z ON l.source=z.source AND l.external_id=z.external_id AND l.observed_at=z.observed_at WHERE l.price>0"""
    rows=[dict(r) for r in db.execute(q,(cutoff,))]; db.close()
    for r in rows:
        try: r["extra"]=json.loads(r.get("extra_json") or "{}")
        except Exception: r["extra"]={}
    return rows


def _age_h(row):
    d=_parse_ts(row.get("observed_at","")); return 1e9 if d is None else max(0.0,(_now()-d).total_seconds()/3600)

def _freshness(row, half_life_h=6.0): return math.exp(-math.log(2.0)*_age_h(row)/max(half_life_h,1e-6))

def _group_key(row):
    k=entity_key(row); return k if k.startswith(("g:","id:","fp:")) else ""


class ShadowLiveEngine:
    """Paper-only live collector -> model stack -> 10k capital-day allocator."""
    def __init__(self, capital=10_000.0, snapshot_db="data/roman_snapshots.sqlite", tracking_db="data/roman_tracking.sqlite",
                 dashboard_path="outputs/live/dashboard.json", fx_path="data/fx_rates.json", queries_per_source=2, rows_per_query=40):
        self.capital=float(capital); self.snapshot_db=snapshot_db; self.tracking_db=tracking_db; self.dashboard_path=Path(dashboard_path)
        self.dashboard_path.parent.mkdir(parents=True,exist_ok=True); self.fx_path=fx_path; self.queries_per_source=int(queries_per_source); self.rows_per_query=int(rows_per_query)
        self.assumptions,self.venues,self.sectors=load_config(); self.fees=FeeEngine(self.venues)
        self.model=SimpleModelStack(min_lcb_roi=max(.002,float(self.assumptions.get("min_lcb_roi",.003))), lcb_z=max(1.0,float(self.assumptions.get("lcb_z",1.28))))
        self.allocator=CapitalDayAllocator(capital=self.capital,cash_buffer_fraction=.10); self.plan=build_query_plan(); self.adapters=official_adapters()
        self.started_at=_now(); self.nav_series=[{"t":_iso(),"nav":self.capital}]; self.feed_state={}

    def refresh_fx(self):
        b=FXBook.load(self.fx_path); age=b.age_hours()
        if b.source=="missing" or age is None or age>20:
            try: refresh_ecb(self.fx_path,friction_pct=float(os.getenv("ROMAN_FX_FRICTION","0.004"))); b=FXBook.load(self.fx_path)
            except Exception: pass
        return b

    def collect_cycle(self):
        store=SnapshotStore(self.snapshot_db); sch=AdaptiveQueryScheduler(self.tracking_db); counts={}
        for source,adapter in self.adapters.items():
            if not adapter.available(): self.feed_state[source]={"status":"NO_CREDENTIALS","rows":0,"last":_iso()}; continue
            chosen=sch.choose(source,self.plan.get(source,[]),self.queries_per_source); total=0; err=""
            for q in chosen:
                try:
                    rows=list(adapter.fetch(q,limit=self.rows_per_query))
                    for r in rows: r.extra=dict(r.extra or {},query=q)
                    store.append(rows); sch.record_scan(source,q,len(rows)); total+=len(rows)
                except Exception as e: err=str(e)[:240]; sch.record_error(source,q,err)
            counts[source]=total; self.feed_state[source]={"status":"OK" if not err else ("PARTIAL" if total else "ERROR"),"rows":total,"last":_iso(),"error":err}
        sch.close(); store.close(); return counts

    def _sector(self,row):
        q=str((row.get("extra") or {}).get("query") or "").lower(); title=str(row.get("title") or "").lower(); best=(0,None)
        for s in self.sectors.values():
            n=s.name.lower(); score=3 if q==n and q else 2 if q and (q in n or n in q) else 1 if s.family and s.family.lower() in title else 0
            if score>best[0]: best=(score,s)
        return (best[1].key,best[1].family) if best[1] else ("unknown","")

    def build_candidates(self):
        rows=_latest_rows(self.snapshot_db,12); fx=self.refresh_fx(); groups=defaultdict(list)
        for r in rows:
            k=_group_key(r)
            if not k: continue
            eur=fx.to_eur(float(r["price"]),str(r.get("currency") or ""),False)
            if eur and eur>0: rr=dict(r,entity_key=k,price_eur=eur); groups[k].append(rr)
        out=[]
        for k,g in groups.items():
            if len({r["source"] for r in g})<2 and not any((r.get("extra") or {}).get("highest_bid") for r in g): continue
            for buy in g:
                sk,fam=self._sector(buy); s=self.sectors.get(sk)
                if s is None: continue
                buy_eur=fx.acquisition_eur(float(buy["price"]),str(buy.get("currency") or ""))
                if not buy_eur: continue
                comps=[]; best=None; best_net=-1e18
                for comp in g:
                    if comp["source"]==buy["source"] and comp["external_id"]==buy["external_id"]: continue
                    src=str(comp["source"]); gross=float(comp["price_eur"]); v=self.venues.get(src); fee=float(v.sell_fee) if v else .12; fixed=float(v.fixed_exit) if v else 0.; vh=float(v.price_haircut) if v else 0.
                    gross_mark=gross*(1-vh)*.97; net=gross_mark*(1-fee)-fixed; fr=_freshness(comp)
                    comps.append({"net_value":net,"freshness":fr,"executable_confidence":.35,"source":src})
                    if net*fr>best_net: best_net=net*fr; best=(src,gross_mark,fee,fixed)
                locked=None
                for comp in g:
                    hb=(comp.get("extra") or {}).get("highest_bid")
                    if hb in (None,"",0,"0") or _age_h(comp)>1.5: continue
                    b=fx.to_eur(float(hb),str(comp.get("currency") or ""),True)
                    if b and (locked is None or b>locked[0]): locked=(b,str(comp["source"]))
                if best is None and locked is None: continue
                exit_src,gross_mark,exit_fee,exit_fixed=best if best else (locked[1],locked[0],.12,0.)
                acq=buy_eur*(1+s.buy_cost_pct)+s.buy_fixed; problem=acq*s.problem_prob*s.problem_loss
                c={"entity_key":k,"sector":s.key,"family":fam,"product":k,"title":buy.get("title",""),"buy_source":buy["source"],"buy_external_id":buy["external_id"],"buy_url":buy.get("url",""),
                   "buy_price":buy_eur,"buy_fee_rate":s.buy_cost_pct,"buy_fixed":s.buy_fixed,"base_fair_value":float(gross_mark),"exit_source":exit_src,"exit_fee_rate":float(exit_fee),"exit_fixed":float(exit_fixed),
                   "expected_fraud_loss":float(problem),"model_sigma_roi":max(.018,float(s.model_sigma)),"seller_route_key":f"{buy['source']}:{buy.get('seller','')}->{exit_src}","comparables_net":comps,"buy_query":str((buy.get("extra") or {}).get("query") or "")}
                if locked:
                    v=self.venues.get(locked[1]); c.update(locked_exit_bid=float(locked[0]),exit_source=locked[1],exit_fee_rate=float(v.sell_fee) if v else .12,exit_fixed=float(v.fixed_exit) if v else 0.,locked=True)
                sc=self.model.score(c); row=dict(c)
                row.update(trade=sc.trade,fair_value=sc.fair_value,acquisition_cost=sc.acquisition_cost,expected_exit_net=sc.expected_exit_net,fair_value_net_roi=sc.fair_value_net_roi,factor_net_roi=sc.factor_net_roi,anomaly_net_roi=sc.anomaly_net_roi,
                           locked_net_roi=sc.locked_net_roi,expected_holding_days=sc.expected_holding_days,sale_prob_30d=sc.sale_prob_30d,seller_success_prob=sc.seller_success_prob,condition_risk=sc.condition_risk,regime_weight=sc.regime_weight,
                           ensemble_confidence=sc.ensemble_confidence,conservative_net_roi=sc.conservative_net_roi,lcb_net_roi=sc.lcb_net_roi,score_per_capital_day=sc.score_per_capital_day,reason=sc.reason)
                out.append(row)
        return sorted(out,key=lambda x:float(x.get("score_per_capital_day",-1e9)),reverse=True)

    def allocate(self,candidates): return list(self.allocator.allocate([c for c in candidates if c.get("trade")]).selected)

    def dashboard_payload(self,candidates,basket):
        deployed=sum(float(x.get("acquisition_cost",0)) for x in basket); elapsed=(_now()-self.started_at).total_seconds()/3600
        ops=[{"entity":c.get("title") or c.get("entity_key"),"buy_source":c.get("buy_source"),"exit_source":c.get("exit_source"),"cost":c.get("acquisition_cost"),"net_edge":c.get("conservative_net_roi"),"lcb_roic":c.get("lcb_net_roi"),"expected_days":c.get("expected_holding_days"),"score_day":c.get("score_per_capital_day"),"confidence":c.get("ensemble_confidence"),"qualified":bool(c.get("trade")),"url":c.get("buy_url",""),"reason":c.get("reason","")} for c in candidates[:40]]
        return {"brand":"Reselling BOT","status":"SHADOW-LIVE" if any(v.get("status")=="OK" for v in self.feed_state.values()) else "PRE-SHADOW","updated_at":_iso(),"capital":self.capital,"nav":self.capital,"net_pnl":0.0,"deployed":deployed,
                "open_positions":len(basket),"locked_positions":sum(1 for x in basket if x.get("locked")),"raw_signals":len(candidates),"qualified_signals":sum(1 for c in candidates if c.get("trade")),
                "avg_net_roic":(sum(float(x.get("lcb_net_roi",0)) for x in basket)/len(basket)) if basket else None,"experiment":{"label":"48H SHADOW","elapsed_hours":elapsed,"target_hours":48},"nav_series":self.nav_series[-600:],
                "opportunities":ops,"feeds":[dict(source=k,**v) for k,v in sorted(self.feed_state.items())],"model_status":{"Hierarchical fair value":"ONLINE","PCA residual factors":"WARMUP","Dynamic Kalman factors":"WARMUP","Sale hazard / liquidity":"ONLINE","Seller-quality posterior":"ONLINE","Text + image condition risk":"ONLINE","Regime detector":"ONLINE","Cross-market anomaly":"ONLINE","Conservative ensemble":"ONLINE"}}

    def run_cycle(self):
        counts=self.collect_cycle(); candidates=self.build_candidates(); basket=self.allocate(candidates); p=self.dashboard_payload(candidates,basket); p["cycle_rows"]=counts
        self.dashboard_path.write_text(json.dumps(p,indent=2,ensure_ascii=False)); return p
