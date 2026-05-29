from pymercator.engines.ranking import rank_assets
from pymercator.engines.regime import classify_market_regime
from pymercator.loaders import load_universe_csv
from pymercator.policy import load_policy


def test_raw_signal_and_context_signal_are_separated():
    policy = load_policy("config/policy.json")
    assets = load_universe_csv("data/universes/ibov_sample.csv")

    regime = classify_market_regime(
        headline_risk="ACTIVE",
        headline_tags=["IRAN", "OIL"],
        market_trend="CHOPPY",
        market_volatility="NORMAL",
        policy=policy,
    )

    rows = rank_assets(
        assets=assets,
        regime=regime,
        policy=policy,
    )

    prio3 = next(row for row in rows if row.ticker == "PRIO3")

    assert prio3.raw_score > prio3.context_score
    assert prio3.raw_signal == "BUY"
    assert prio3.context_signal in {"NEUTRAL", "AVOID"}