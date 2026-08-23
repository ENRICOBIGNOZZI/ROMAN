from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FDRResult:
    selected: tuple[str, ...]
    mean_false_probability: float
    alpha: float


class PosteriorFDRSelector:
    """Simple Bayesian-style error-budget gate for the wide universe.

    `ensemble_confidence` is treated as a provisional posterior success
    probability. Until it is forward-calibrated, this is deliberately a
    conservative *selection gate*, not a claim of exact frequentist FDR control.
    We select the largest confidence-ranked prefix whose mean local false
    probability (1-confidence) does not exceed alpha.
    """

    def __init__(self, alpha: float = 0.25):
        self.alpha=max(0.0,min(1.0,float(alpha)))

    def select(self, candidates: list[dict]) -> FDRResult:
        rows=[]
        for c in candidates:
            if not c.get("trade"):
                continue
            conf=max(0.0,min(1.0,float(c.get("ensemble_confidence",0.0) or 0.0)))
            local_false=1.0-conf
            key=str(c.get("entity_key") or c.get("buy_external_id") or id(c))
            rows.append((local_false,key,c))
        rows.sort(key=lambda x:(x[0],-float(x[2].get("score_per_capital_day",0.0) or 0.0)))
        chosen=[]; running=0.0
        for lf,key,_ in rows:
            new_mean=(running+lf)/(len(chosen)+1)
            if new_mean<=self.alpha:
                chosen.append(key); running+=lf
            else:
                break
        mean=running/max(len(chosen),1) if chosen else 0.0
        return FDRResult(tuple(chosen),mean,self.alpha)

    def annotate(self, candidates: list[dict]) -> FDRResult:
        result=self.select(candidates); selected=set(result.selected)
        for c in candidates:
            key=str(c.get("entity_key") or c.get("buy_external_id") or id(c))
            c["fdr_selected"]=bool(c.get("trade") and key in selected)
            if c.get("trade") and not c["fdr_selected"]:
                c["reason"]=str(c.get("reason") or "")+"|posterior_fdr_gate"
        return result
