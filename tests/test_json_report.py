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


def test_daily_report_json_can_embed_multi_horizon_prediction():
    report = run_daily_pipeline(
        universe_path="data/universes/ibov_sample.csv",
        universe_name="IBOV",
        profile="AGR",
        headline_risk="OFF",
        headline_tags=[],
        market_trend="UP",
        market_volatility="NORMAL",
    )

    payload = daily_report_to_dict(
        report,
        prediction={
            "engine_used": "multi_horizon_ridge",
            "horizons": [5, 20, 60],
            "d5_score": 51.0,
            "d20_score": 58.0,
            "d60_score": 66.0,
            "combined_score": 59.85,
            "dominant_horizon": "D60",
            "behavior": "POSITIONAL_SETUP",
            "weights": {"D5": 0.25, "D20": 0.35, "D60": 0.4},
        },
    )

    assert payload["prediction"]["engine"] == "multi_horizon_ridge"
    assert payload["prediction"]["horizons"] == [5, 20, 60]
    assert payload["decisions"][0]["prediction"]["d5_score"] == 51.0
    assert payload["decisions"][0]["prediction"]["d20_score"] == 58.0
    assert payload["decisions"][0]["prediction"]["d60_score"] == 66.0
    assert payload["decisions"][0]["prediction"]["behavior"] == "POSITIONAL_SETUP"
