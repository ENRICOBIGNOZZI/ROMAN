#!/usr/bin/env python3
import argparse, json
from pathlib import Path
import pandas as pd
from roman_arb.simulator import run_simulation

p=argparse.ArgumentParser()
p.add_argument("--capital",type=float,default=20000)
p.add_argument("--years",type=int,default=250)
p.add_argument("--days",type=int,default=365)
p.add_argument("--seed",type=int,default=1000)
p.add_argument("--out",default="outputs")
p.add_argument("--arrival-multiplier",type=float,default=None)
p.add_argument("--edge-shrinkage",type=float,default=None)
a=p.parse_args()
rows=[]
for i in range(a.years):
    r=run_simulation(a.capital,a.days,a.seed+i,arrival_multiplier=a.arrival_multiplier,edge_shrinkage=a.edge_shrinkage)
    rows.append(r.summary)
df=pd.DataFrame(rows)
out=Path(a.out);out.mkdir(exist_ok=True)
df.to_csv(out/f"mc_{int(a.capital)}.csv",index=False)
summary={
 "capital":a.capital,"years":a.years,
 "return_mean":float(df["return"].mean()),"return_median":float(df["return"].median()),
 "return_p10":float(df["return"].quantile(.10)),"return_p90":float(df["return"].quantile(.90)),
 "utilization_mean":float(df["utilization"].mean()),"trades_mean":float(df["trades"].mean()),
 "turnover_mean":float(df["turnover"].mean()),"loss_year_fraction":float((df["return"]<0).mean())
}
(out/f"mc_{int(a.capital)}_summary.json").write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
