from pathlib import Path

from pymercator.data.prices_csv import (
    check_prices_dir,
    validate_price_csv,
    write_price_rows_csv,
)


def test_write_and_validate_price_csv(tmp_path: Path):
    output = tmp_path / "PRIO3.SA.csv"

    write_price_rows_csv(
        output,
        [
            {
                "date": "2025-01-02",
                "open": 10.0,
                "high": 11.0,
                "low": 9.5,
                "close": 10.5,
                "volume": 1000,
            },
            {
                "date": "2025-01-03",
                "open": 10.5,
                "high": 11.5,
                "low": 10.0,
                "close": 11.0,
                "volume": 1200,
            },
        ],
    )

    payload = validate_price_csv(output)

    assert payload["valid"] is True
    assert payload["rows"] == 2
    assert payload["start_date"] == "2025-01-02"
    assert payload["end_date"] == "2025-01-03"


def test_check_prices_dir_reports_valid_files(tmp_path: Path):
    output = tmp_path / "VALE3.SA.csv"

    write_price_rows_csv(
        output,
        [
            {
                "date": "2025-01-02",
                "open": 60.0,
                "high": 61.0,
                "low": 59.0,
                "close": 60.5,
                "volume": 5000,
            }
        ],
    )

    payload = check_prices_dir(tmp_path)

    assert payload["exists"] is True
    assert payload["files"] == 1
    assert payload["valid_files"] == 1
    assert payload["invalid_files"] == 0
