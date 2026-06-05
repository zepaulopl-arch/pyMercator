from pathlib import Path

from pymercator.basket import run_daily_basket
from pymercator.cli_update import _build_update_status
from pymercator.pipeline import run_daily_pipeline
from pymercator.position_actions import build_position_actions
from pymercator.reports.json_report import daily_report_to_dict


def test_daily_report_contract_contains_required_sections(tmp_path: Path):
    report = run_daily_pipeline(
        universe_path="data/universes/ibov_sample.csv",
        universe_name="IBOV",
        profile="CON",
        headline_risk="OFF",
        headline_tags=[],
        market_trend="DOWN",
        market_volatility="HIGH",
    )
    update_status = _build_update_status(status="OK", steps=[], warnings=[])
    position_actions = build_position_actions(
        report,
        positions_path=tmp_path / "missing_positions.csv",
    )
    payload = daily_report_to_dict(
        report,
        prediction={
            "engine_used": "multi_horizon_ridge",
            "horizons": [5, 20, 60],
            "model_quality": {"status": "WEAK", "edge": -0.01},
        },
        blockers_count={},
        update_status=update_status,
        basket={"status": "BLOCKED", "assets": 0, "slots": 5},
        observation_candidates=[],
        position_actions=position_actions,
        market_context={
            "schema_version": "market_context.v2",
            "regime_summary": {"market_regime": "RISK_OFF"},
        },
    )

    for field in (
        "schema_version",
        "profile",
        "market_regime",
        "prediction",
        "model_quality",
        "decision",
        "blockers",
        "basket",
        "observation_candidates",
        "short_observation_candidates",
        "position_actions",
        "market_context",
    ):
        assert field in payload
    assert payload["schema_version"] == "daily_report.v1"
    assert payload["update_status"]["schema_version"] == "update_status.v1"
    assert "freshness" in payload["update_status"]
    assert payload["position_actions"]["schema_version"] == "position_actions.v1"
    assert payload["market_context"]["schema_version"] == "market_context.v2"


def test_basket_json_contract_for_blocked_basket(tmp_path: Path):
    output = tmp_path / "basket.csv"
    payload = run_daily_basket(output_csv=output, eligible_tickers=[])

    assert payload["schema_version"] == "basket.v1"
    assert payload["status"] == "BLOCKED"
    assert payload["assets"] == 0
    assert payload["slots"] == 5
    assert payload["execution_mode"] == "ANALYSIS_ONLY"
    assert output.with_suffix(".json").exists()


def test_update_status_contract_contains_freshness():
    payload = _build_update_status(status="OK", steps=[], warnings=[])

    for field in (
        "schema_version",
        "status",
        "impact",
        "context_valid",
        "regime_reliability",
        "freshness",
    ):
        assert field in payload
    assert payload["schema_version"] == "update_status.v1"
    assert payload["freshness"]["freshness_status"] == "OK"
