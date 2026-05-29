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
                "date": (date(2025, 3, 2) + timedelta(days=index)).isoformat(),
                "open": round(close - 0.1, 2),
                "high": round(close + 0.2, 2),
                "low": round(close - 0.2, 2),
                "close": round(close, 2),
                "volume": 3000000 + index * 1000,
            }
        )

    write_price_rows_csv(path, rows)


def test_real_pack_command_with_skip_fetch(tmp_path: Path, capsys):
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

    exit_code = main(
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

    assert exit_code == 0
    assert universe_output.exists()

    captured = capsys.readouterr()
    assert "PYMERCATOR REAL PACK SUMMARY" in captured.out
    assert "STATUS" in captured.out
    assert "OK" in captured.out
