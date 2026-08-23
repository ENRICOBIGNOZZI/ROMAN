# Pure arbitrage in ROMAN

ROMAN now treats pure arbitrage as a separate execution problem from predictive reselling.

For the same normalized entity `i`, venue `a` supplies an executable buy ask and venue `b` supplies an executable sell bid.  The raw spread is never used directly.  ROMAN computes

```text
acquisition_cost = ask_a * (1 + buy_fee_rate) + buy_fixed_costs
locked_exit_net  = bid_b * (1 - sell_fee_rate) - sell_fixed_costs
locked_profit    = locked_exit_net - acquisition_cost
locked_net_roi   = locked_profit / acquisition_cost
```

The fixed-cost buckets include shipping, tax, authentication, FX and route-specific costs.  Quantity is capped at the minimum immediately executable quantity across both legs.

Because physical-market resale is generally not atomic, a positive locked spread is not enough.  The engine also requires:

- both prices to be explicitly executable rather than public indicative asks;
- fresh quotes;
- acceptable execution latency;
- sufficient joint fill probability;
- route risk below the level where leg risk erases the spread;
- positive conservative ROI after a second-leg-failure penalty.

The pure-arbitrage path deliberately does not use fair-value, PCA, Kalman or anomaly forecasts.  Those belong to statistical arbitrage / ordinary reselling.  Capital allocation should rank a valid pure arbitrage by conservative net ROI per capital-day and give it priority over forecast-dependent opportunities when risk and operational constraints are comparable.
