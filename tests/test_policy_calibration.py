from pymercator.policy import load_policy


def test_policy_uses_annualized_volatility_calibration():
    policy = load_policy("config/policy.json")

    assert policy["calibration"]["volatility_pct_basis"] == "annualized"
    assert policy["trade_validation"]["max_volatility_pct"] >= 55.0
    assert policy["universe_health"]["max_volatility_pct"] >= 55.0


def test_profiles_have_risk_specific_volatility_limits():
    policy = load_policy("config/policy.json")

    assert (
        policy["profiles"]["CON"]["max_volatility_pct"]
        < policy["profiles"]["AGR"]["max_volatility_pct"]
    )
    assert (
        policy["profiles"]["BAL"]["max_volatility_pct"]
        < policy["profiles"]["RLX"]["max_volatility_pct"]
    )
    assert (
        policy["profiles"]["CON"]["max_atr_pct"]
        < policy["profiles"]["AGR"]["max_atr_pct"]
    )
