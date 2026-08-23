# ROMAN unified resale model

ROMAN uses one predictive model, not a collection of models that vote on a purchase.

For candidate item `i` at time `t`, the core object is

`p(net_payoff_i, time_to_sale_i | item_information_i, market_state_t)`.

The implementation has four blocks:

1. **Market state.** PCA/Kalman/regime information summarizes common market conditions. It can only make a bounded adjustment to the predictive distribution.
2. **Price + time-to-sale prediction.** Hierarchical partial pooling (`product -> family -> sector -> global`) estimates sparse fair values; condition, seller/route quality and cross-market comparables enter as covariates/evidence. Sale hazard estimates the time needed to recycle capital.
3. **Net payoff distribution.** All fees, shipping, authentication, FX, repair, expected returns/fraud and taxes are deducted before computing expected ROI and its uncertainty.
4. **Decision.** The engine uses one lower-confidence bound,

`LCB(net_ROI) = E[net_ROI] - z * sigma(net_ROI)`,

and ranks candidates by

`score = LCB(net_ROI) / E[holding_days]`.

The capital allocator then applies cash, concentration, duplicate and slow-inventory constraints.

## Interpretation of the old components

- **Partial pooling** is part of the price model, not a separate model.
- **PCA/Kalman/regime detection** describe the same latent market state.
- **Cross-market comparables** are noisy measurements of the same exit value.
- **Seller and condition models** are covariates/risk inputs to the same payoff distribution.
- **Sale hazard** supplies the time component of the same economic prediction.
- **Locked executable exits** are high-information observations, not another forecasting model.

The old agreement-gated ensemble is therefore not part of the core architecture. A new component is useful only if it improves forward calibration of net payoff or time-to-sale.

## Net economics

Acquisition capital is

`buy_price * (1 + buy_fee_rate) + buy_fixed + buy_shipping + buy_tax`.

Expected exit cash is fully net of configured exit costs. The system optimizes expected economic payoff per capital-day, not gross spread and not capital utilization.

ROMAN remains shadow/paper software: no real orders are submitted by the model stack.
