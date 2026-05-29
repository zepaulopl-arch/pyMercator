from pymercator.engines.universe import evaluate_universe_health
from pymercator.loaders import load_universe_csv
from pymercator.policy import load_policy


def test_universe_health_classifies_sample():
    policy = load_policy("config/policy.json")
    assets = load_universe_csv("data/universes/ibov_sample.csv")

    result = evaluate_universe_health(
        universe_name="IBOV",
        assets=assets,
        policy=policy,
    )

    assert result.total_assets > 0
    assert result.valid_assets > 0
    assert result.healthy_assets >= 0
    assert result.health.value in {"BROAD", "NORMAL", "NARROW", "BROKEN"}