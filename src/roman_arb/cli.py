from __future__ import annotations

import argparse

from .simulator import run_simulation, save_result


def main():
    p = argparse.ArgumentParser(
        prog="roman-sim",
        description="Synthetic Monte Carlo simulator for the ROMAN resale model",
    )
    p.add_argument("--capital", type=float, default=20000)
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--config", default=None)
    p.add_argument("--out", default="outputs")
    p.add_argument("--arrival-multiplier", type=float, default=None)
    p.add_argument("--edge-shrinkage", type=float, default=None)
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()
    r = run_simulation(
        args.capital,
        args.days,
        args.seed,
        args.config,
        args.verbose,
        args.arrival_multiplier,
        args.edge_shrinkage,
    )
    save_result(r, args.out, prefix=f"sim_{int(args.capital)}")
    for k, v in r.summary.items():
        print(f"{k:32s}: {v}")
