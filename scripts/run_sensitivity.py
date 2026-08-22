#!/usr/bin/env python3
import argparse
from pathlib import Path
import pandas as pd
from roman_arb.simulator import run_simulation

p=argparse.ArgumentParser()
p.add_argument("--capital",type=float,default=20000)
p.add_argument("--arrival",nargs="+",type=float,default=[0.5,1,2,4])
p.add_argument("--shrink",nargs="+",type=float,default=[0.50,0.55,0.60,0.65])
p.add_argument("--years",type=int,default=20)
p.add_argument("--seed",type=int,default=9000)
p.add_argument("--out",default="outputs")
a=p.parse_args()
rows=[]
for ar in a.arrival:
  for sh in a.shrink:
    vals=[]
    for i in range(a.years):
      vals.append(run_simulation(a.capital,365,a.seed+i,arrival_multiplier=ar,edge_shrinkage=sh).summary)
    d=pd.DataFrame(vals)
    rows.append({"arrival_multiplier":ar,"edge_shrinkage":sh,"return_median":d["return"].median(),"return_mean":d["return"].mean(),"p10":d["return"].quantile(.1),"p90":d["return"].quantile(.9),"utilization":d["utilization"].mean(),"trades":d["trades"].mean(),"turnover":d["turnover"].mean()})
out=Path(a.out);out.mkdir(exist_ok=True)
df=pd.DataFrame(rows);df.to_csv(out/"sensitivity.csv",index=False)
print(df.to_string(index=False,float_format=lambda x:f"{x:.4f}"))
