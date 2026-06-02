import csv
import json
from pathlib import Path

from pymercator.cli import main
from pymercator.data.universe_csv import REQUIRED_COLUMNS
from pymercator.ui import (
    color_metric,
    colorize,
    metric_status,
    set_color_mode,
    short_sector,
    strip_ansi,
)
from pymercator.ui.colors import ANSI_RE


def test_color_flags_control_terminal_output(capsys) -> None:
    exit_code = main(["diag", "--color", "always"])

    assert exit_code == 0
    assert "\x1b[" in capsys.readouterr().out

    exit_code = main(["diag", "--no-color"])

    assert exit_code == 0
    assert "\x1b[" not in capsys.readouterr().out


def test_strip_ansi_and_status_classes() -> None:
    blocked = colorize("BLOCKED", "BLOCKED", enabled=True)
    ok = colorize("OK", "OK", enabled=True)

    assert "\x1b[" in blocked
    assert "\x1b[" in ok
    assert strip_ansi(blocked) == "BLOCKED"
    assert strip_ansi(ok) == "OK"


def test_metric_color_classes() -> None:
    weak_trend = color_metric(30, "trend", width=5, enabled=True)
    warning_vol = color_metric(60, "vol", width=5, enabled=True)
    high_atr = color_metric(9, "atr", width=5, enabled=True)

    assert metric_status("trend", 70) == "OK"
    assert metric_status("mom", 50) == "WATCH"
    assert metric_status("mom", 30) == "WEAK"
    assert metric_status("vol", 90) == "HIGH"
    assert metric_status("atr", 9) == "HIGH"
    assert "\x1b[" in weak_trend
    assert "\x1b[" in warning_vol
    assert "\x1b[" in high_atr
    assert strip_ansi(weak_trend).strip() == "30"


def test_sector_abbreviations_are_stable() -> None:
    assert short_sector("consumer_discretionary") == "consumer_disc."
    assert short_sector("consumer_staples") == "consumer_stap."
    assert short_sector("communication") == "comm."
    assert short_sector("health_care") == "health"


def test_universe_details_colors_core_metrics(tmp_path: Path, capsys) -> None:
    universe = tmp_path / "universe.csv"
    rows = [
        {
            "ticker": "BAD3",
            "sector": "consumer_discretionary",
            "last_close": "10",
            "avg_volume_brl": "100000000",
            "trend_score": "30",
            "momentum_score": "35",
            "volatility_pct": "70",
            "atr_pct": "9",
            "liquidity_score": "90",
            "quality_score": "50",
            "news_score": "50",
            "entry": "10",
            "stop": "9",
            "target": "12",
        }
    ]
    with universe.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    exit_code = main(
        [
            "universe",
            "diagnose",
            "--file",
            str(universe),
            "--details",
            "--color",
            "always",
        ]
    )

    assert exit_code in {0, 1}
    output = capsys.readouterr().out
    asset_line = next(line for line in output.splitlines() if line.startswith("BAD3"))
    assert asset_line.count("\x1b[") >= 4
    assert strip_ansi(asset_line).split()[2:6] == ["70.0", "9.0", "30.0", "35.0"]


def test_colorized_scenario_does_not_write_ansi_artifacts(
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
            "--color",
            "always",
        ]
    )

    assert exit_code == 0
    assert "\x1b[" in capsys.readouterr().out

    basket_json = basket_csv.with_suffix(".json")
    basket_txt = basket_csv.with_suffix(".txt")
    for path in [report_txt, report_json, basket_csv, basket_json, basket_txt]:
        text = path.read_text(encoding="utf-8")
        assert not ANSI_RE.search(text), path

    report_payload = json.loads(report_json.read_text(encoding="utf-8"))
    basket_payload = json.loads(basket_json.read_text(encoding="utf-8"))
    assert report_payload["basket"]["status"] == "OK"
    assert basket_payload["status"] == "OK"

    set_color_mode("auto")
