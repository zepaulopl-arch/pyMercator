from pathlib import Path

from pymercator.data.prices_csv import write_price_rows_csv
from pymercator.data.universe_builder import (
    build_asset_from_price_file,
    build_universe_csv_from_prices,
)


def _write_price_file(path: Path) -> None:
    rows = []

    for index in range(80):
        close = 10.0 + index * 0.05
        rows.append(
            {
                "date": (
                    f"2025-03-{(index % 28) + 1:02d}"
                    if index < 28
                    else f"2025-04-{(index % 28) + 1:02d}"
                ),
                "open": round(close - 0.05, 2),
                "high": round(close + 0.15, 2),
                "low": round(close - 0.15, 2),
                "close": round(close, 2),
                "volume": 1000000 + index * 1000,
            }
        )

    write_price_rows_csv(path, rows)


def test_build_asset_uses_sector_map_override(tmp_path: Path):
    price_file = tmp_path / "PRIO3.SA.csv"
    _write_price_file(price_file)

    asset = build_asset_from_price_file(
        price_file,
        sector_map={"PRIO3": "CustomOil"},
    )

    assert asset["ticker"] == "PRIO3"
    assert asset["sector"] == "CustomOil"


def test_build_universe_uses_tickers_file_as_sector_source(tmp_path: Path):
    prices_dir = tmp_path / "prices"
    output = tmp_path / "universe.csv"
    tickers = tmp_path / "tickers.csv"

    prices_dir.mkdir()
    _write_price_file(prices_dir / "PRIO3.SA.csv")

    tickers.write_text(
        "ticker,sector\nPRIO3.SA,CustomOil\n",
        encoding="utf-8",
    )

    payload = build_universe_csv_from_prices(
        prices_dir=prices_dir,
        output=output,
        tickers_file=tickers,
    )

    assert payload["asset_count"] == 1
    assert payload["assets"][0]["sector"] == "CustomOil"
    assert output.exists()
