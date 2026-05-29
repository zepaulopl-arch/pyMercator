from pymercator.pipeline import run_daily_pipeline


def test_daily_pipeline_generates_report():
    report = run_daily_pipeline(
        universe_path="data/universes/ibov_sample.csv",
        universe_name="IBOV",
        profile="AGR",
        headline_risk="ACTIVE",
        headline_tags=["IRAN", "OIL"],
        market_trend="CHOPPY",
        market_volatility="NORMAL",
    )

    assert report.universe_name == "IBOV"
    assert report.profile == "AGR"
    assert report.market_regime.headline_risk.value == "ACTIVE"
    assert len(report.decisions) > 0