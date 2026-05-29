from pymercator.explain import decision_codes, decision_label
from pymercator.pipeline import run_daily_pipeline


def test_decision_codes_include_headline_sector_and_cap_for_prio3_active():
    report = run_daily_pipeline(
        universe_path="data/universes/ibov_sample.csv",
        universe_name="IBOV",
        profile="AGR",
        headline_risk="ACTIVE",
        headline_tags=["IRAN", "OIL", "WAR"],
        market_trend="CHOPPY",
        market_volatility="NORMAL",
    )

    prio3 = next(item for item in report.decisions if item.asset.ticker == "PRIO3")

    codes = decision_codes(prio3)

    assert "HEADLINE" in codes
    assert "SECTOR" in codes
    assert "CAP" in codes
    assert decision_label(prio3) == "+".join(codes)


def test_decision_codes_include_regime_deny_for_extreme():
    report = run_daily_pipeline(
        universe_path="data/universes/ibov_sample.csv",
        universe_name="IBOV",
        profile="AGR",
        headline_risk="EXTREME",
        headline_tags=["IRAN", "OIL", "WAR"],
        market_trend="CHOPPY",
        market_volatility="NORMAL",
    )

    prio3 = next(item for item in report.decisions if item.asset.ticker == "PRIO3")

    assert "REGIME_DENY" in decision_codes(prio3)
