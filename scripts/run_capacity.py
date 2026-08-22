#!/usr/bin/env python3
import argparse
import pandas as pd
from pathlib import Path
from roman_arb.simulator import run_simulation

p=argparse.ArgumentParser()
p.add_argument("--capitals",nargs="+",type=float,default=[2500,5000,10000,20000,25000,50000,100000])
p.add_argument("--years",type=int,default=80)
p.add_argument("--days",type=int,default=365)
p.add_argument("--seed",type=int,default=7000)
p.add_argument("--out",default="outputs")
p.add_argument("--arrival-multiplier",type=float,default=None)
p.add_argument("--edge-shrinkage",type=float,default=None)
a=p.parse_args()
rows=[]
for c in a.capitals:
    vals=[]
    for i in range(a.years):
        vals.append(run_simulation(c,a.days,a.seed+i,arrival_multiplier=a.arrival_multiplier,edge_shrinkage=a.edge_shrinkage).summary)
    d=pd.DataFrame(vals)
    rows.append({"capital":c,"return_mean":d["return"].mean(),"return_median":d["return"].median(),"p10":d["return"].quantile(.1),"p90":d["return"].quantile(.9),"utilization":d["utilization"].mean(),"trades":d["trades"].mean(),"turnover":d["turnover"].mean(),"pnl_mean":d["pnl"].mean()})
out=Path(a.out);out.mkdir(exist_ok=True)
df=pd.DataFrame(rows);df.to_csv(out/"capacity_curve.csv",index=False)
print(df.to_string(index=False,float_format=lambda x:f"{x:.4f}"))
