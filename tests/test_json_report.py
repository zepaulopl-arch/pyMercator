import json

from pymercator.pipeline import run_daily_pipeline
from pymercator.reports.json_report import (
    daily_report_to_dict,
    render_daily_report_json,
)


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
    assert payload["decisions"][0]["ref_price"] is not None
    assert payload["decisions"][0]["ref_ts"].endswith("Z")
    assert payload["decisions"][0]["ref_source"] != "daily_report.asset.last_close"


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
            "horizon_alignment": "DIVERGENT",
            "dominance_strength": "STRONG",
            "horizon_scores": {"D5": 51.0, "D20": 58.0, "D60": 66.0},
            "horizon_spread": 15.0,
            "weights": {"D5": 0.25, "D20": 0.35, "D60": 0.4},
        },
    )

    assert payload["prediction"]["engine"] == "multi_horizon_ridge"
    assert payload["prediction"]["horizons"] == [5, 20, 60]
    assert payload["prediction"]["horizon_alignment"] == "DIVERGENT"
    assert payload["prediction"]["dominance_strength"] == "STRONG"
    assert payload["prediction"]["horizon_scores"] == {
        "D5": 51.0,
        "D20": 58.0,
        "D60": 66.0,
    }
    assert payload["prediction"]["horizon_spread"] == 15.0
    assert payload["decisions"][0]["prediction"]["d5_score"] == 51.0
    assert payload["decisions"][0]["prediction"]["d20_score"] == 58.0
    assert payload["decisions"][0]["prediction"]["d60_score"] == 66.0
    assert payload["decisions"][0]["prediction"]["behavior"] == "POSITIONAL_SETUP"
    assert payload["decisions"][0]["prediction"]["horizon_alignment"] == "DIVERGENT"
    assert payload["decisions"][0]["prediction"]["dominance_strength"] == "STRONG"


def test_daily_report_json_attaches_reference_prices_to_review_rows():
    report = run_daily_pipeline(
        universe_path="data/universes/ibov_sample.csv",
        universe_name="IBOV",
        profile="CON",
        headline_risk="OFF",
        headline_tags=[],
        market_trend="DOWN",
        market_volatility="HIGH",
    )
    first = report.decisions[0]
    ticker = first.asset.ticker

    payload = daily_report_to_dict(
        report,
        observation_candidates=[
            {
                "ticker": ticker,
                "score": 75.0,
                "class": "OBS_FAVORABLE",
                "bias": "LONG",
                "executable": False,
            }
        ],
        position_actions={
            "short_candidates": [
                {
                    "ticker": ticker,
                    "score": 91.0,
                    "class": "SHORT_SETUP",
                    "borrow_status": "DATA_MISSING",
                    "permission": "SHORT_BLOCKED",
                }
            ],
            "short_observation_candidates": [
                {
                    "ticker": ticker,
                    "score": 91.0,
                    "class": "SHORT_SETUP",
                    "borrow_status": "DATA_MISSING",
                    "permission": "SHORT_BLOCKED",
                }
            ],
        },
    )

    reference_price = payload["decisions"][0]["ref_price"]
    reference_source = payload["decisions"][0]["ref_source"]
    for row in (
        payload["decisions"][0],
        payload["observation_candidates"][0],
        payload["short_candidates"][0],
        payload["short_observation_candidates"][0],
    ):
        assert row["ref_price"] == reference_price
        assert row["ref_ts"].endswith("Z")
        assert row["ref_source"] == reference_source
