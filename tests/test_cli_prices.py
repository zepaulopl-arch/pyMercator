from pathlib import Path

from pymercator.cli import main
from pymercator.data.prices_csv import write_price_rows_csv


def test_prices_check_command_accepts_valid_price_dir(tmp_path: Path, capsys):
    write_price_rows_csv(
        tmp_path / "PRIO3.SA.csv",
        [
            {
                "date": "2025-01-02",
                "open": 10.0,
                "high": 11.0,
                "low": 9.5,
                "close": 10.5,
                "volume": 1000,
            }
        ],
    )

    exit_code = main(
        [
            "prices",
            "check",
            "--prices-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0

    captured = capsys.readouterr()
    assert "PYMERCATOR PRICES CHECK" in captured.out
    assert "VALID FILES" in captured.out
    assert "PRIO3.SA.csv" in captured.out


def test_prices_check_command_returns_error_for_missing_dir(tmp_path: Path):
    missing = tmp_path / "missing"

    exit_code = main(
        [
            "prices",
            "check",
            "--prices-dir",
            str(missing),
        ]
    )

    assert exit_code == 1
