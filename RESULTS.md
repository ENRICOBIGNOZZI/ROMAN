# Example research results

These numbers are **synthetic paper-trading outputs**, not claims of achievable returns.
They are committed only to make the current calibration auditable.

## Base EUR 20,000 run

Current default calibration (`arrival_multiplier=1.0`, `edge_shrinkage=0.60`), seed 7, 365 simulated days:

- terminal cash: EUR 24,074.86
- return: 20.37%
- trades: 181
- mean realized trade ROI: 3.90%
- average utilization: 15.15%
- turnover: 5.22x
- win rate: 90.1%

The high win rate is a model output and is precisely one of the parameters that must be challenged with real forward data.

## EUR 20,000 Monte Carlo

30 synthetic years, current default calibration:

- mean return: 19.82%
- median return: 19.36%
- 10th percentile: 17.67%
- 90th percentile: 22.30%
- mean utilization: 16.64%
- mean trades/year: 177.7
- mean turnover: 5.62x

The narrow Monte Carlo range is **conditional on the calibration**. It does not represent model uncertainty. The arrival/edge sensitivity below is much more important.

## Capacity curve (small research run)

The committed `outputs/example_capacity_curve.csv` uses 8 synthetic years per capital level. Approximate median returns:

| Capital | Median return | Mean utilization |
|---:|---:|---:|
| EUR 2.5k | 50.4% | 33.6% |
| EUR 5k | 49.1% | 34.2% |
| EUR 10k | 38.7% | 28.3% |
| **EUR 20k** | **21.1%** | **16.1%** |
| EUR 25k | 15.4% | 12.8% |
| EUR 50k | 8.2% | 6.7% |
| EUR 100k | 4.1% | 3.4% |

This curve is a direct consequence of the assumed opportunity firehose. It is not empirical capacity evidence.

## Arrival x edge-shrinkage sensitivity

Two structural parameters dominate the result:

- `arrival_multiplier`: number of prefiltered candidates observed;
- `edge_shrinkage`: fraction of apparent discount that survives hidden-quality / stale-comps / optimizer's-curse correction.

Selected examples from the committed sensitivity file:

| Arrival multiplier | Edge shrinkage | Median annual return | Utilization |
|---:|---:|---:|---:|
| 0.5x | 0.50 | 2.3% | 2.7% |
| 1.0x | 0.55 | 8.0% | 9.1% |
| **1.0x** | **0.60** | **20.2%** | **15.2%** |
| 2.0x | 0.55 | 18.8% | 16.2% |
| 4.0x | 0.50 | 12.4% | 17.3% |
| 4.0x | 0.60 | 75.2% | 49.4% |

The last row is intentionally not presented as plausible. It demonstrates why **real point-in-time arrival rates and executable-edge decay must be measured before trusting the strategy**.

## What to validate first

1. Actual candidate arrival rate after exact entity matching.
2. Fraction of apparent discount surviving condition/quality normalization.
3. Fill probability conditional on apparent edge.
4. Realized net exit price rather than public fair-value marks.
5. Time-to-sale distribution.
6. Returns/fraud/service losses.
7. Account-specific fees, shipping and FX.

Only a forward paper feed can identify these quantities reliably.
