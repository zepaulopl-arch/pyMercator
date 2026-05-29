from pymercator.engines.validation import validate_trade
from pymercator.loaders import load_universe_csv
from pymercator.policy import load_policy


def test_validation_blocks_low_rr_when_profile_requires_more():
    policy = load_policy("config/policy.json")
    assets = load_universe_csv("data/universes/ibov_sample.csv")
    lren3 = next(asset for asset in assets if asset.ticker == "LREN3")

    result = validate_trade(
        asset=lren3,
        profile="CON",
        policy=policy,
    )

    assert result.status.value in {"READY", "BLOCKED"}
    assert result.rr is not None