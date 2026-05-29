from pymercator.explain import decision_codes, decision_label
from pymercator.pipeline import run_daily_pipeline


def test_watch_without_specific_risk_is_caution_not_ok():
    report = run_daily_pipeline(
        universe_path="data/universes/ibov_sample.csv",
        universe_name="IBOV",
        profile="CON",
        headline_risk="OFF",
        headline_tags=[],
        market_trend="CHOPPY",
        market_volatility="NORMAL",
    )

    prio3 = next(item for item in report.decisions if item.asset.ticker == "PRIO3")

    assert prio3.permission.status.value == "WATCH"
    assert decision_codes(prio3) == ("CAUTION",)
    assert decision_label(prio3) == "CAUTION"


def test_decision_codes_do_not_mix_ok_with_negative_codes():
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
    codes = decision_codes(prio3)

    assert "REGIME_DENY" in codes
    assert "OK" not in codes
