import json

from pymercator.pipeline import run_daily_pipeline
from pymercator.reports.json_report import daily_report_to_dict, render_daily_report_json


def test_daily_report_json_contains_core_sections():
    report = run_daily_pipeline(
        universe_path="data/universes/ibov_sample.csv",
        universe_name="IBOV",
        profile="AGR",
        headline_risk="ACTIVE",
        headline_tags=["IRAN", "OIL"],
        market_trend="CHOPPY",
        market_volatility="NORMAL",
    )

    payload = daily_report_to_dict(report)

    assert payload["universe_name"] == "IBOV"
    assert payload["profile"] == "AGR"
    assert payload["market_regime"]["headline_risk"] == "ACTIVE"
    assert payload["universe_health"]["total_assets"] > 0
    assert len(payload["decisions"]) > 0


def test_render_daily_report_json_is_valid_json():
    report = run_daily_pipeline(
        universe_path="data/universes/ibov_sample.csv",
        universe_name="IBOV",
        profile="AGR",
        headline_risk="EXTREME",
        headline_tags=["IRAN", "OIL", "WAR"],
        market_trend="CHOPPY",
        market_volatility="NORMAL",
    )

    text = render_daily_report_json(report)
    payload = json.loads(text)

    assert payload["posture"] == "STAND_ASIDE"
    assert payload["market_regime"]["permission"] == "DENY"
