from pymercator.pipeline import run_daily_pipeline
from pymercator.reports.json_report import daily_report_to_dict


def test_json_report_contains_decision_codes_and_label():
    report = run_daily_pipeline(
        universe_path="data/universes/ibov_sample.csv",
        universe_name="IBOV",
        profile="AGR",
        headline_risk="ACTIVE",
        headline_tags=["IRAN", "OIL", "WAR"],
        market_trend="CHOPPY",
        market_volatility="NORMAL",
    )

    payload = daily_report_to_dict(report)
    prio3 = next(
        item
        for item in payload["decisions"]
        if item["asset"]["ticker"] == "PRIO3"
    )

    assert "decision_codes" in prio3
    assert "decision_label" in prio3
    assert "HEADLINE" in prio3["decision_codes"]
    assert "SECTOR" in prio3["decision_codes"]
