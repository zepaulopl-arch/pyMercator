import json
from datetime import date, timedelta
from pathlib import Path

from pymercator.cli import main
from pymercator.data.prices_csv import write_price_rows_csv


def _write_price_file(path: Path) -> None:
    rows = []

    for index in range(80):
        close = 20.0 + index * 0.1
        rows.append(
            {
                "date": (date(2025, 1, 2) + timedelta(days=index)).isoformat(),
                "open": round(close - 0.1, 2),
                "high": round(close + 0.2, 2),
                "low": round(close - 0.2, 2),
                "close": round(close, 2),
                "volume": 2000000 + index * 1000,
            }
        )

    write_price_rows_csv(path, rows)


def test_packs_command_marks_real_pack_type(tmp_path: Path, capsys):
    prices_dir = tmp_path / "prices"
    tickers_file = tmp_path / "tickers.csv"
    universe_output = tmp_path / "universe.csv"
    run_dir = tmp_path / "scenario_runs"

    prices_dir.mkdir()
    _write_price_file(prices_dir / "PRIO3.SA.csv")

    tickers_file.write_text(
        "ticker,sector\nPRIO3.SA,CustomOil\n",
        encoding="utf-8",
    )

    real_exit = main(
        [
            "real-pack",
            "--tickers-file",
            str(tickers_file),
            "--start",
            "2025-01-01",
            "--prices-dir",
            str(prices_dir),
            "--universe-output",
            str(universe_output),
            "--run-dir",
            str(run_dir),
            "--headline-tags",
            "IRAN,OIL,WAR",
            "--skip-fetch",
        ]
    )

    assert real_exit == 0

    index_exit = main(
        [
            "packs",
            "--run-dir",
            str(run_dir),
        ]
    )

    assert index_exit == 0

    captured = capsys.readouterr()
    assert "PYMERCATOR PACK INDEX" in captured.out
    assert "REAL" in captured.out
    assert "WARN_SMALL_UNIV" in captured.out or "WARN_SMALL_UNIVERSE" in captured.out

    json_exit = main(
        [
            "packs",
            "--run-dir",
            str(run_dir),
            "--json",
        ]
    )

    assert json_exit == 0

    captured = capsys.readouterr()
    json_start = captured.out.find("[")
    payload = json.loads(captured.out[json_start:])

    assert payload[0]["type"] == "REAL"
    assert payload[0]["source_command"] == "real-pack"
    assert payload[0]["universe_assets"] == 1
    assert payload[0]["prices_valid_files"] == 1
    assert payload[0]["diagnosis_status"] == "WARN_SMALL_UNIVERSE"
