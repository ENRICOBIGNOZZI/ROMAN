# ROMAN opportunity priority

ROMAN should classify opportunities before capital allocation:

1. `pure_locked_arbitrage`: executable buy ask and executable sell bid are both available now; no fair-value forecast is required.
2. `statistical_arbitrage`: a cross-market or factor residual is unusually large, but the exit is not locked.
3. `reselling_alpha`: expected exit value exceeds fully loaded acquisition cost after predictive/risk adjustments.

The allocator should compare all three on conservative net return per capital-day subject to cash, inventory, venue, seller, concentration and operational constraints.  The label `pure_locked_arbitrage` is reserved for trades that pass the explicit execution gates in `PureArbitrageEngine`.
