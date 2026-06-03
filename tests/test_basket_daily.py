import csv
import json
import subprocess
import sys
from pathlib import Path

from pymercator import basket as basket_mod


def _write_daily_prices(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for day in range(1, 20):
        rows.append({
            "date": f"2026-05-{day:02d}",
            "open": 100 + day,
            "high": 101 + day,
            "low": 99 + day,
            "close": 100 + day,
            "volume": 1000 + day,
        })
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["date", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(rows)


def _write_csv_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def test_run_daily_basket_creates_outputs(tmp_path: Path) -> None:
    prices_dir = tmp_path / "prices"
    universe_path = tmp_path / "universe.csv"
    matrix_path = tmp_path / "feature_matrix.csv"
    evaluation_path = tmp_path / "evaluation.json"
    output_csv = tmp_path / "basket.csv"

    universe_rows = [
        {"ticker": "ABC3.SA", "sector": "Energy"},
        {"ticker": "DEF3.SA", "sector": "Financial"},
        {"ticker": "GHI3.SA", "sector": "Energy"},
        {"ticker": "JKL3.SA", "sector": "Industrial"},
    ]
    _write_csv_rows(universe_path, universe_rows)

    matrix_rows = [
        {
            "ticker": "ABC3.SA",
            "sector": "Energy",
            "momentum_score": "0.9",
            "trend_score": "0.8",
            "news_score": "0.7",
            "return_5d": "0.03",
            "volatility_20d": "0.12",
            "atr_pct": "1.5",
        },
        {
            "ticker": "DEF3.SA",
            "sector": "Financial",
            "momentum_score": "0.7",
            "trend_score": "0.6",
            "news_score": "0.5",
            "return_5d": "0.02",
            "volatility_20d": "0.10",
            "atr_pct": "1.8",
        },
        {
            "ticker": "GHI3.SA",
            "sector": "Energy",
            "momentum_score": "0.8",
            "trend_score": "0.7",
            "news_score": "0.4",
            "return_5d": "0.01",
            "volatility_20d": "0.15",
            "atr_pct": "1.7",
        },
        {
            "ticker": "JKL3.SA",
            "sector": "Industrial",
            "momentum_score": "0.85",
            "trend_score": "0.75",
            "news_score": "0.65",
            "return_5d": "0.025",
            "volatility_20d": "0.11",
            "atr_pct": "1.6",
        },
    ]
    _write_csv_rows(matrix_path, matrix_rows)

    evaluation_path.write_text(json.dumps({"summary": {"best_accuracy": 0.8}}), encoding="utf-8")

    for row in matrix_rows:
        chart = prices_dir / f"{row['ticker']}.csv"
        _write_daily_prices(chart)

    payload = basket_mod.run_daily_basket(
        slots=2,
        min_sectors=2,
        min_weight=0.10,
        capital=100000.0,
        risk_per_trade=0.005,
        targets=2,
        stop_mode="progressive",
        prices_dir=str(prices_dir),
        universe=str(universe_path),
        matrix=str(matrix_path),
        evaluation=str(evaluation_path),
        output_csv=str(output_csv),
    )

    assert payload["status"] == "OK"
    assert output_csv.exists()
    assert output_csv.with_suffix(".json").exists()
    assert output_csv.with_suffix(".txt").exists()
    assert len(payload["rows"]) == 2
    assert len({row["sector"] for row in payload["rows"]}) >= 2
    assert all(row["quantity"] > 0 for row in payload["rows"])


def test_run_daily_basket_blocks_empty_actionable_set(tmp_path: Path) -> None:
    output_csv = tmp_path / "basket.csv"

    payload = basket_mod.run_daily_basket(
        slots=5,
        min_sectors=3,
        min_weight=0.10,
        capital=100000.0,
        risk_per_trade=0.005,
        targets=2,
        stop_mode="progressive",
        prices_dir=str(tmp_path / "prices"),
        universe=str(tmp_path / "universe.csv"),
        matrix=str(tmp_path / "feature_matrix.csv"),
        evaluation=str(tmp_path / "evaluation.json"),
        output_csv=str(output_csv),
        eligible_tickers=[],
    )

    assert payload["status"] == "BLOCKED"
    assert payload["reason"] == "no actionable assets"
    assert payload["rows"] == []
    assert output_csv.exists()
    assert json.loads(output_csv.with_suffix(".json").read_text(encoding="utf-8"))["rows"] == []


def test_run_daily_basket_filters_out_non_actionable_tickers(tmp_path: Path) -> None:
    prices_dir = tmp_path / "prices"
    universe_path = tmp_path / "universe.csv"
    matrix_path = tmp_path / "feature_matrix.csv"
    evaluation_path = tmp_path / "evaluation.json"
    output_csv = tmp_path / "basket.csv"

    _write_csv_rows(
        universe_path,
        [
            {"ticker": "READY3", "sector": "Energy"},
            {"ticker": "BLOCK3", "sector": "Energy"},
        ],
    )
    _write_csv_rows(
        matrix_path,
        [
            {
                "ticker": "READY3",
                "sector": "Energy",
                "momentum_score": "0.4",
                "trend_score": "0.4",
                "news_score": "0.4",
                "return_5d": "0.01",
                "volatility_20d": "0.12",
                "atr_pct": "1.5",
            },
            {
                "ticker": "BLOCK3",
                "sector": "Energy",
                "momentum_score": "0.99",
                "trend_score": "0.99",
                "news_score": "0.99",
                "return_5d": "0.05",
                "volatility_20d": "0.08",
                "atr_pct": "1.5",
            },
        ],
    )
    evaluation_path.write_text(json.dumps({}), encoding="utf-8")
    _write_daily_prices(prices_dir / "READY3.SA.csv")
    _write_daily_prices(prices_dir / "BLOCK3.SA.csv")

    payload = basket_mod.run_daily_basket(
        slots=1,
        min_sectors=1,
        min_weight=0.10,
        capital=100000.0,
        risk_per_trade=0.005,
        targets=2,
        stop_mode="progressive",
        prices_dir=str(prices_dir),
        universe=str(universe_path),
        matrix=str(matrix_path),
        evaluation=str(evaluation_path),
        output_csv=str(output_csv),
        eligible_tickers=["READY3"],
    )

    assert payload["status"] == "OK"
    assert [row["ticker"] for row in payload["rows"]] == ["READY3"]


def test_ready_tickers_from_daily_report_ignores_blocked_assets(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "decisions": [
                    {
                        "asset": {"ticker": "READY3"},
                        "permission": {"status": "READY"},
                    },
                    {
                        "asset": {"ticker": "BLOCK3"},
                        "permission": {"status": "BLOCKED"},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    assert basket_mod.ready_tickers_from_daily_report(report) == ["READY3"]


def test_basket_summary_uses_short_sector_labels() -> None:
    payload = {
        "status": "OK",
        "slots": 1,
        "min_sectors": 1,
        "min_weight": 0.10,
        "capital": 100000.0,
        "risk_per_trade": 0.005,
        "stop_mode": "progressive",
        "targets": 2,
        "rows": [
            {
                "ticker": "LREN3",
                "sector": "consumer_discretionary",
                "rank": 1,
                "score": 0.5,
                "entry": 10.0,
                "initial_stop": 9.5,
                "target_1": 10.5,
                "target_2": 11.0,
                "quantity": 100,
                "status": "OK",
            }
        ],
        "warnings": [],
    }

    summary = basket_mod.render_basket_summary(payload)

    assert "cons_disc" in summary
    assert "consumer_discretionary" not in summary
    assert "min_weight         0.10" in summary
    assert "risk_per_trade     0.50%" in summary
    assert payload["rows"][0]["sector"] == "consumer_discretionary"


def test_cli_basket_daily_runs(tmp_path: Path) -> None:
    prices_dir = tmp_path / "prices"
    universe_path = tmp_path / "universe.csv"
    matrix_path = tmp_path / "feature_matrix.csv"
    evaluation_path = tmp_path / "evaluation.json"
    output_csv = tmp_path / "basket.csv"

    universe_rows = [
        {"ticker": "ABC3.SA", "sector": "Energy"},
        {"ticker": "DEF3.SA", "sector": "Financial"},
    ]
    _write_csv_rows(universe_path, universe_rows)

    matrix_rows = [
        {
            "ticker": "ABC3.SA",
            "sector": "Energy",
            "momentum_score": "0.9",
            "trend_score": "0.8",
            "news_score": "0.7",
            "return_5d": "0.03",
            "volatility_20d": "0.12",
            "atr_pct": "1.5",
        },
        {
            "ticker": "DEF3.SA",
            "sector": "Financial",
            "momentum_score": "0.7",
            "trend_score": "0.6",
            "news_score": "0.5",
            "return_5d": "0.02",
            "volatility_20d": "0.10",
            "atr_pct": "1.8",
        },
    ]
    _write_csv_rows(matrix_path, matrix_rows)
    evaluation_path.write_text(json.dumps({}), encoding="utf-8")

    for row in matrix_rows:
        chart = prices_dir / f"{row['ticker']}.csv"
        _write_daily_prices(chart)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pymercator.cli",
            "basket",
            "daily",
            "--slots",
            "1",
            "--min-sectors",
            "1",
            "--prices-dir",
            str(prices_dir),
            "--universe",
            str(universe_path),
            "--matrix",
            str(matrix_path),
            "--evaluation",
            str(evaluation_path),
            "--output",
            str(output_csv),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "PYMERCATOR DAILY BASKET" in result.stdout
    assert "FILES" in result.stdout
    assert output_csv.exists()


def test_cli_basket_show_reads_latest_json(tmp_path: Path) -> None:
    prices_dir = tmp_path / "prices"
    universe_path = tmp_path / "universe.csv"
    matrix_path = tmp_path / "feature_matrix.csv"
    evaluation_path = tmp_path / "evaluation.json"
    output_csv = tmp_path / "basket.csv"

    universe_rows = [
        {"ticker": "ABC3.SA", "sector": "Energy"},
    ]
    _write_csv_rows(universe_path, universe_rows)

    matrix_rows = [
        {
            "ticker": "ABC3.SA",
            "sector": "Energy",
            "momentum_score": "0.9",
            "trend_score": "0.8",
            "news_score": "0.7",
            "return_5d": "0.03",
            "volatility_20d": "0.12",
            "atr_pct": "1.5",
        },
    ]
    _write_csv_rows(matrix_path, matrix_rows)
    evaluation_path.write_text(json.dumps({}), encoding="utf-8")

    _write_daily_prices(prices_dir / "ABC3.SA.csv")

    basket_mod.run_daily_basket(
        slots=1,
        min_sectors=1,
        min_weight=0.10,
        capital=100000.0,
        risk_per_trade=0.005,
        targets=2,
        stop_mode="progressive",
        prices_dir=str(prices_dir),
        universe=str(universe_path),
        matrix=str(matrix_path),
        evaluation=str(evaluation_path),
        output_csv=str(output_csv),
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pymercator.cli",
            "basket",
            "show",
            "--output",
            str(output_csv),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "PYMERCATOR DAILY BASKET" in result.stdout
    assert "FILES" in result.stdout
    assert "assets" in result.stdout
    assert " 1" in result.stdout
    assert "ABC3.SA" not in result.stdout
    assert result.stdout.count("-" * 80) == 2
