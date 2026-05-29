import json
from datetime import date, timedelta
from pathlib import Path

from pymercator.cli import main
from pymercator.data.prices_csv import write_price_rows_csv


def _write_price_file(path: Path) -> None:
    rows = []

    for index in range(80):
        close = 30.0 + index * 0.1
        rows.append(
            {
                "date": (date(2025, 1, 2) + timedelta(days=index)).isoformat(),
                "open": round(close - 0.1, 2),
                "high": round(close + 0.2, 2),
                "low": round(close - 0.2, 2),
                "close": round(close, 2),
                "volume": 3000000 + index * 1000,
            }
        )

    write_price_rows_csv(path, rows)


def test_daily_real_context_file_snapshot_is_recorded_in_manifest(tmp_path: Path):
    prices_dir = tmp_path / "prices"
    tickers_file = tmp_path / "tickers.csv"
    universe_output = tmp_path / "ibov_live.csv"
    run_dir = tmp_path / "scenario_runs"
    context_file = tmp_path / "market_context_auto.json"

    prices_dir.mkdir()
    _write_price_file(prices_dir / "PRIO3.SA.csv")

    tickers_file.write_text(
        "ticker,sector\nPRIO3.SA,energy\n",
        encoding="utf-8",
    )

    context_file.write_text(
        json.dumps(
            {
                "headline_tags": ["RISK_OFF"],
                "market_trend": "DOWN",
                "market_volatility": "NORMAL",
                "notes": "automatic context test",
                "source": "auto_indices",
                "metrics": {
                    "ibov_return_20d_pct": -5.24,
                    "brent_return_20d_pct": -21.92,
                },
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "daily-real",
            "--tickers-file",
            str(tickers_file),
            "--prices-dir",
            str(prices_dir),
            "--universe-output",
            str(universe_output),
            "--run-dir",
            str(run_dir),
            "--context",
            str(context_file),
            "--skip-fetch",
        ]
    )

    assert exit_code == 0

    pack = sorted(run_dir.iterdir())[-1]
    manifest = json.loads((pack / "00_manifest.json").read_text(encoding="utf-8"))
    manifest_txt = (pack / "00_manifest.txt").read_text(encoding="utf-8")

    snapshot = manifest["context_snapshot"]

    assert snapshot["headline_tags"] == ["RISK_OFF"]
    assert snapshot["market_trend"] == "DOWN"
    assert snapshot["market_volatility"] == "NORMAL"
    assert snapshot["source"] == "auto_indices"
    assert snapshot["metrics"]["ibov_return_20d_pct"] == -5.24
    assert snapshot["context_source"] == "file"
    assert snapshot["context_file"] == str(context_file)
    assert "CONTEXT SNAPSHOT" in manifest_txt
