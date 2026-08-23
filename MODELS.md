# ROMAN simple model stack

ROMAN deliberately starts with small, interpretable online models. Every decision metric is computed after explicit fees/costs and then converted into lower-confidence-bound net ROIC per capital-day.

## 0. Pure executable arbitrage

Pure arbitrage is handled separately from predictive reselling. For the same normalized entity, ROMAN requires an executable buy ask on one venue and an executable sell bid on another venue. It computes the fully loaded acquisition cost and locked exit proceeds after buy/sell fees, shipping, tax, authentication, FX and route-specific costs.

Because physical resale is not atomic, a raw positive spread is not enough. `PureArbitrageEngine` also checks minimum executable quantity, joint fill probability, quote staleness, execution latency, route risk and a second-leg-failure penalty. Only opportunities with positive conservative net ROI are labeled `pure_locked_arbitrage`.

Ordinary public listing dispersion is never treated as pure arbitrage unless the feed explicitly marks the two sides as executable.

## 1. Hierarchical fair value

Executed/trusted net-equivalent log prices are modeled through

`product -> family -> sector -> global`.

Each child mean is shrunk to its parent by `n/(n+kappa)`. Sparse products therefore cannot generate extreme fair values from one observation.

## 2. PCA + dynamic Kalman factors

PCA is fitted only to normalized returns of homogeneous series, never raw price levels. The factor overlay is bounded. A local-level Kalman filter tracks each factor online:

`F_t = F_{t-1} + eta_t`, `y_t = F_t + eps_t`.

If product loadings are available, ROMAN uses `item_return - beta' F_t` as the dynamic residual. Factor information can only modestly adjust an existing valuation signal.

## 3. Liquidity / sale hazard

For each sector/family segment, a Gamma-Poisson posterior estimates the daily sale hazard:

`lambda = (a0 + sales)/(b0 + exposure_days)`.

Price gap and condition risk enter only through bounded multipliers. Then

`P(T_sale <= h) = 1 - exp(-lambda h)` and `E[T_sale] = 1/lambda`.

This directly enters the capital-day denominator.

## 4. Seller / route posterior

Seller or seller-route reliability is Beta-Binomial:

`p_good = alpha/(alpha+beta)`.

New sellers start close to 50%; repeated successful forward outcomes raise the posterior. Low-reliability sellers receive a risk penalty and reduce ensemble confidence.

## 5. Text + image condition risk

A small transparent text model flags damage, repair, missing parts, replica/fake, as-is, untested, etc. Positive evidence such as sealed/authenticated/full-set reduces risk modestly. The model accepts an optional external `image_defect_score` so a future vision model can plug in without changing downstream logic.

Condition risk applies a bounded haircut to fair value; it is never treated only as volatility.

## 6. Regime detection

An EWMA + Page-Hinkley style detector tracks market/sector returns. In a detected stress regime, old model information is shrunk rather than extrapolated unchanged.

## 7. Cross-market anomaly model

For same-entity net-equivalent comparables, ROMAN uses a weighted median and weighted MAD. Freshness and executable-confidence weights shrink public asks that are stale or weakly executable.

## 8. Conservative ensemble

The predictive model signals are:

- hierarchical/fair-value net ROI;
- factor-residual net ROI;
- robust cross-market anomaly net ROI.

Without a locked spread, at least two model signals must agree. The ensemble uses a conservative lower location between the 25th percentile and median, then multiplies by seller, condition, liquidity and regime gates.

A validated pure locked arbitrage is evaluated by the separate execution engine and does not need model agreement, but it still cannot bypass operational, quality, liquidity or execution-risk controls.

## Net-cost objective

For a candidate, acquisition capital is

`buy_price * (1 + buy_fee_rate) + buy_fixed + buy_shipping + buy_tax`.

Expected exit cash is

`fair_value * (1 - exit_fee_rate) - exit_fixed - exit_shipping - authentication - FX - repair - expected_returns - expected_fraud - exit_tax`.

ROMAN then computes

`net_ROIC = (exit_net - acquisition_cost)/acquisition_cost`

and finally

`score = LCB(net_ROIC) / E[holding_days]`.

For pure arbitrage, the analogous score uses the conservative locked net ROI divided by capital-days.

The live allocator should maximize this score under the EUR 10,000 cash/inventory constraints, not gross spread and not capital utilization.

## Design principle

Adding more models must improve forward calibration, not mechanically increase the number of trades. Every new layer is bounded/shrunk until the 24h/48h shadow outcomes demonstrate predictive value.
