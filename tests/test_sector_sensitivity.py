from pymercator.engines.ranking import rank_assets
from pymercator.engines.regime import classify_market_regime
from pymercator.loaders import load_universe_csv
from pymercator.policy import load_policy


def test_sector_sensitivity_changes_context_factor_by_sector():
    policy = load_policy("config/policy.json")
    assets = load_universe_csv("data/universes/ibov_sample.csv")

    regime = classify_market_regime(
        headline_risk="ACTIVE",
        headline_tags=["IRAN", "OIL", "WAR"],
        market_trend="CHOPPY",
        market_volatility="NORMAL",
        policy=policy,
    )

    rows = rank_assets(
        assets=assets,
        regime=regime,
        policy=policy,
    )

    by_ticker = {row.ticker: row for row in rows}

    prio3 = by_ticker["PRIO3"]
    lren3 = by_ticker["LREN3"]

    assert prio3.context_factor > lren3.context_factor
    assert prio3.context_score > lren3.context_score
    assert "sector factor" in "; ".join(prio3.reasons)


def test_off_headline_keeps_context_factor_near_one():
    policy = load_policy("config/policy.json")
    assets = load_universe_csv("data/universes/ibov_sample.csv")

    regime = classify_market_regime(
        headline_risk="OFF",
        headline_tags=[],
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

    assert prio3.context_factor == 1.0
    assert prio3.raw_score == prio3.context_score
