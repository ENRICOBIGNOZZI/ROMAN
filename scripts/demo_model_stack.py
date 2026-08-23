from roman_arb.model_stack import SimpleModelStack


def main():
    m = SimpleModelStack(min_lcb_roi=0.003, lcb_z=1.28)
    for _ in range(10):
        m.sellers.update("demo-seller|ebay", True, 0.02)

    candidate = {
        "buy_price": 100.0,
        "buy_fee_rate": 0.02,
        "buy_shipping": 4.0,
        "base_fair_value": 125.0,
        "exit_fee_rate": 0.09,
        "exit_shipping": 5.0,
        "authentication_cost": 2.0,
        "fx_cost": 0.5,
        "expected_return_loss": 1.0,
        "expected_fraud_loss": 0.5,
        "sector": "tcg_graded",
        "family": "pokemon",
        "product": "demo-card",
        "title": "PSA 10 authenticated",
        "image_count": 8,
        "seller_route_key": "demo-seller|ebay",
        "factor_residual_z": -1.0,
        "factor_confidence": 0.5,
        "comparables_net": [
            {"net_value": 118.0, "freshness": 1.0, "executable_confidence": 0.8},
            {"net_value": 121.0, "freshness": 0.9, "executable_confidence": 0.7},
            {"net_value": 119.0, "freshness": 0.8, "executable_confidence": 0.8},
            {"net_value": 123.0, "freshness": 0.7, "executable_confidence": 0.6},
        ],
        "model_sigma_roi": 0.01,
    }
    s = m.score(candidate)
    print(f"acquisition_cost       {s.acquisition_cost:8.2f}")
    print(f"expected_exit_net      {s.expected_exit_net:8.2f}")
    print(f"fair_value_net_roi     {100*s.fair_value_net_roi:8.2f}%")
    print(f"factor_net_roi         {100*(s.factor_net_roi or 0):8.2f}%")
    print(f"anomaly_net_roi        {100*(s.anomaly_net_roi or 0):8.2f}%")
    print(f"sale_prob_30d          {100*s.sale_prob_30d:8.2f}%")
    print(f"expected_holding_days  {s.expected_holding_days:8.2f}")
    print(f"conservative_net_roi   {100*s.conservative_net_roi:8.2f}%")
    print(f"lcb_net_roi            {100*s.lcb_net_roi:8.2f}%")
    print(f"score_per_capital_day  {100*s.score_per_capital_day:8.4f}%")
    print(f"trade                  {s.trade}")
    print(f"reason                 {s.reason}")


if __name__ == "__main__":
    main()
