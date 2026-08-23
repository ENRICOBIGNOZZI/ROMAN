# ROMAN simple model stack

ROMAN starts with small, interpretable online models. Monetary inputs are normalized to EUR and decision metrics are computed after explicit costs, then expressed as lower-confidence-bound net ROIC per capital-day.

## 1. Hierarchical fair value

Trusted gross-equivalent valuation observations are modeled through

`product -> family -> sector -> global`.

Each child log-price mean is shrunk to its parent by `n/(n+kappa)`. Sparse products therefore cannot create extreme fair values from one observation. The hierarchy stores a valuation state; venue costs are applied later by the selected exit route rather than embedded repeatedly in fair value.

Only trusted execution/settlement-style observations should update this layer. Public asks are not silently promoted into trusted training targets.

## 2. PCA + dynamic Kalman factors

PCA is fitted only to temporal returns, never raw price levels. In the live engine, returns are formed within the **same entity and source across cycles** so changes in marketplace composition do not masquerade as price moves.

The factor overlay is bounded. A local-level Kalman filter tracks each factor online:

`F_t = F_{t-1} + eta_t`, `y_t = F_t + eps_t`.

If product loadings are available, ROMAN uses `item_return - beta' F_t` as the dynamic residual. PCA/factor information cannot create a large trade from nothing; it can only modestly modify a pre-existing valuation edge.

## 3. Liquidity / sale hazard

For each sector/family segment, a Gamma-Poisson posterior estimates the daily sale hazard:

`lambda = (a0 + sales)/(b0 + exposure_days)`.

Price gap and condition risk enter only through bounded multipliers. Crucially, the price-gap covariate is based on the **planned resale ask relative to fair value**, not the acquisition price. Buying cheaply must not mechanically imply faster resale.

Then

`P(T_sale <= h) = 1 - exp(-lambda h)` and `E[T_sale] = 1/lambda`.

This enters the capital-day denominator. A fresh executable exit is handled separately and does not use the inventory sale-hazard forecast as if it still needed a buyer.

## 4. Seller / route posterior

Seller or seller-route reliability is Beta-Binomial:

`p_good = alpha/(alpha+beta)`.

The posterior is updated only from explicit seller/route quality outcomes such as fulfilment, authenticity, return/fraud, or description accuracy. Trading P&L and favorable price marks do **not** count as seller success.

Low-reliability sellers receive an additive risk penalty and reduce confidence. In a pure price-shadow run without seller-quality labels, this posterior correctly remains prior-driven.

## 5. Condition risk

The current live path uses transparent text/metadata evidence from title and marketplace condition fields. It flags damage, repair, missing parts, replica/fake, as-is, untested, etc.; positive evidence such as sealed/authenticated/full-set reduces risk modestly.

The API accepts optional `image_count` and `image_defect_score` inputs so a future vision model can plug in without changing downstream logic, but **no vision model is currently connected**.

Condition risk applies a bounded haircut to valuation and uncertainty; it is not merely a volatility flag.

## 6. Regime detection

A two-sided EWMA + Page-Hinkley-style detector tracks market/sector returns. Persistent positive and negative shifts are both detectable. A detected stress state is held briefly rather than disappearing after the next quiet observation, so old model information is temporarily shrunk instead of being extrapolated unchanged.

## 7. Cross-market anomaly diagnostic

For same-entity net-equivalent comparables, ROMAN uses a weighted median/MAD-style cross-market diagnostic. Freshness and executable-confidence weights reduce the influence of stale or weak asks.

This evidence is not automatically an independent ensemble vote when the fair-value/exit calculation uses the **same comparables**. Otherwise one price discrepancy would be counted twice under different labels.

## 8. Dependence-aware conservative ensemble

A fresh executable bid is a distinct economic object. If its fully net locked ROI is positive enough, it may bypass inventory model agreement and sale-hazard gating, but it still obeys seller, condition, regime, LCB and capital controls.

For a non-locked inventory trade:

1. a positive route/fair-value edge must already exist;
2. the temporal factor channel must add a positive, non-trivial residual confirmation rather than merely copy the fair ROI;
3. seller, condition, liquidity and regime gates must pass;
4. the final LCB net ROI must exceed the hurdle.

A same-comparable anomaly remains diagnostic unless it is explicitly replaced by a separately estimated independent source of evidence.

## 9. Posterior confidence budget

The wide-universe selector keeps the economically best route per entity and applies a confidence-ranked prefix budget. This is useful operationally, but `ensemble_confidence` is **not yet a calibrated posterior probability**, so the current layer must not be described as exact frequentist FDR control.

Calibration requires real forward outcomes.

## Net-cost objective

Acquisition capital is

`buy_price * (1 + buy_fee_rate) + buy_fixed + buy_shipping + buy_tax`.

Fair value is a valuation state, not an exit cash amount. When concrete route evidence exists, expected exit cash is taken from that selected route after its execution markdown, route-specific seller fees, fixed costs, shipping and FX friction. Additional authentication, repair, expected returns/fraud and tax costs are then deducted once.

Only when route evidence is unavailable does the stack fall back to valuing the selected route from fair value.

ROMAN computes

`net_ROIC = (exit_net - acquisition_cost) / acquisition_cost`

and finally

`score = LCB(net_ROIC) / E[holding_days]`.

The live allocator maximizes this score under the EUR 10,000 cash/inventory constraints. It does not maximize gross spread or capital utilization.

## Live-data discipline

- foreign-currency conversion is fail-closed if the FX book is missing, malformed or stale;
- FX reference mids are not executable transaction quotes and receive explicit friction;
- stale executable bids cannot become locked arbitrage;
- HTTP adapters retry bounded transient `429/5xx` failures but do not hide permanent errors;
- credential-gated sources remain `PRE-SHADOW` rather than fabricating data;
- a green zero-row smoke proves software health only, not market validity.

## Design principle

Adding more models must improve forward calibration, not mechanically increase the number of trades. Every new layer is bounded/shrunk until 24h/48h shadow outcomes demonstrate predictive value. Evidence channels that share the same raw observations must not be counted as independent simply because they have different model names.
