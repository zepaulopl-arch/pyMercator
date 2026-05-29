from pymercator.engines.regime import classify_market_regime
from pymercator.policy import load_policy


def test_extreme_headline_denies_market_regime():
    policy = load_policy("config/policy.json")

    result = classify_market_regime(
        headline_risk="EXTREME",
        headline_tags=["IRAN", "OIL"],
        market_trend="UP",
        market_volatility="NORMAL",
        policy=policy,
    )

    assert result.regime.value == "CRISIS"
    assert result.permission.value == "DENY"
    assert result.score_factor == 0.55