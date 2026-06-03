import json
from pathlib import Path

from pymercator.cli import main


def test_positive_operational_scenario_command_releases_actionable_basket(
    tmp_path: Path,
    capsys,
) -> None:
    report_txt = tmp_path / "latest_daily_report.txt"
    report_json = tmp_path / "latest_daily_report.json"
    basket_csv = tmp_path / "latest_daily_basket.csv"

    exit_code = main(
        [
            "scenario",
            "run",
            "--preset",
            "positive_risk_on",
            "--profile",
            "AGR",
            "--basket",
            "--output-root",
            str(tmp_path / "scenarios"),
            "--report-output",
            str(report_txt),
            "--json-output",
            str(report_json),
            "--run-dir",
            str(tmp_path / "run"),
            "--basket-output",
            str(basket_csv),
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    run = payload["run"]

    assert payload["status"] == "OK"
    assert all(payload["checks"].values())
    assert run["market"]["regime"] == "RISK_ON"
    assert run["prediction"]["behavior"] == "TREND_CONFIRM"
    assert run["prediction"]["horizon_alignment"] == "ALIGNED_STRONG"
    assert run["prediction"]["dominance_strength"] == "MODERATE"
    assert run["prediction"]["model_quality"]["status"] == "STRONG"
    assert run["prediction"]["model_quality"]["edge"] > 0
    assert run["decision"]["actionable"] > 0
    assert run["basket"]["status"] == "OK"
    assert run["basket"]["assets"] > 0
    assert all(item["guard"] not in {"BLOCKED", "UNKNOWN"} for item in run["top"])

    basket_payload = json.loads(basket_csv.with_suffix(".json").read_text(encoding="utf-8"))
    assert basket_payload["status"] == "OK"
    assert basket_payload["rows"]
    assert all(str(row["status"]).upper() != "BLOCKED" for row in basket_payload["rows"])

    report_payload = json.loads(report_json.read_text(encoding="utf-8"))
    assert report_payload["prediction"]["engine"] == "multi_horizon_ridge"
    assert report_payload["prediction"]["behavior"] == "TREND_CONFIRM"
    assert report_payload["prediction"]["horizon_alignment"] == "ALIGNED_STRONG"
    assert report_payload["model_quality"] == "STRONG"
    assert "blockers" in report_payload
    assert report_payload["basket"]["status"] == "OK"
    assert report_payload["basket"]["assets"] > 0
