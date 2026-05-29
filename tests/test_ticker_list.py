from pathlib import Path

from pymercator.data.ticker_list import (
    ticker_symbols_from_csv,
    validate_ticker_list_csv,
    write_starter_ticker_list,
)


def test_write_starter_ticker_list_creates_valid_file(tmp_path: Path):
    output = tmp_path / "tickers.csv"

    write_starter_ticker_list(output)

    assert output.exists()

    payload = validate_ticker_list_csv(output)
    tickers = ticker_symbols_from_csv(output)

    assert payload["valid"] is True
    assert payload["rows"] > 5
    assert "PRIO3.SA" in tickers
    assert "VALE3.SA" in tickers
