from pathlib import Path

from pymercator.data.prices_csv import write_price_rows_csv
from pymercator.data.universe_builder import (
    build_asset_from_price_file,
    build_universe_csv_from_prices,
)
from pymercator.data.universe_csv import validate_universe_csv


def _write_price_file(path: Path, start_close: float = 10.0) -> None:
    rows = []

    for index in range(80):
        close = start_close + index * 0.05
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


def test_build_asset_from_price_file_returns_universe_fields(tmp_path: Path):
    price_file = tmp_path / "PRIO3.SA.csv"
    _write_price_file(price_file)

    asset = build_asset_from_price_file(price_file)

    assert asset["ticker"] == "PRIO3"
    assert asset["sector"] == "OilGas"
    assert asset["last_close"] > 0
    assert asset["avg_volume_brl"] > 0
    assert asset["entry"] > asset["stop"]
    assert asset["target"] > asset["entry"]


def test_build_universe_csv_from_prices_creates_valid_universe(tmp_path: Path):
    prices_dir = tmp_path / "prices"
    output = tmp_path / "universe.csv"
    prices_dir.mkdir()

    _write_price_file(prices_dir / "PRIO3.SA.csv", start_close=10.0)
    _write_price_file(prices_dir / "VALE3.SA.csv", start_close=50.0)

    payload = build_universe_csv_from_prices(
        prices_dir=prices_dir,
        output=output,
    )

    assert payload["asset_count"] == 2
    assert payload["error_count"] == 0
    assert output.exists()

    validation = validate_universe_csv(output)
    assert validation["valid"] is True
    assert validation["rows"] == 2

def test_build_universe_csv_from_prices_uses_sentiment_news_score(tmp_path: Path):
    prices_dir = tmp_path / "prices"
    sentiment_dir = tmp_path / "sentiment"
    output = tmp_path / "universe.csv"

    prices_dir.mkdir()
    sentiment_dir.mkdir()

    _write_price_file(prices_dir / "PRIO3.SA.csv", start_close=10.0)

    (sentiment_dir / "PRIO3_SA_sentiment_daily.csv").write_text(
        "date,score,count\n"
        "2025-01-02,0.20,2\n"
        "2025-01-03,0.40,3\n",
        encoding="utf-8",
    )

    payload = build_universe_csv_from_prices(
        prices_dir=prices_dir,
        output=output,
        sentiment_dir=sentiment_dir,
    )

    assert payload["asset_count"] == 1
    assert payload["assets"][0]["news_score"] == 65.0

