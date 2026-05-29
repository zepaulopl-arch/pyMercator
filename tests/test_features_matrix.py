import csv
import json
from datetime import date, timedelta
from pathlib import Path

from pymercator.features_matrix import build_feature_matrix, write_feature_matrix


def _write_price_file(path: Path) -> None:
    lines = ["date,open,high,low,close,volume"]

    for index in range(30):
        day = (date(2025, 1, 2) + timedelta(days=index)).isoformat()
        close = 10.0 + index
        lines.append(f"{day},{close},{close},{close},{close},1000")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_build_feature_matrix_from_universe_prices_and_context(tmp_path: Path):
    universe = tmp_path / "universe.csv"
    prices_dir = tmp_path / "prices"
    context = tmp_path / "context.json"
    features = tmp_path / "features.json"

    prices_dir.mkdir()

    universe.write_text(
        "ticker,sector,last_close,trend_score,momentum_score,volatility_pct,atr_pct,news_score\n"
        "PRIO3,energy,39,60,70,25,3,65\n",
        encoding="utf-8",
    )

    _write_price_file(prices_dir / "PRIO3.SA.csv")

    context.write_text(
        json.dumps(
            {
                "market_trend": "DOWN",
                "market_volatility": "NORMAL",
            }
        ),
        encoding="utf-8",
    )

    features.write_text(
        json.dumps(
            {
                "features": [
                    {"name": "return_1d", "group": "price", "enabled": True},
                    {"name": "return_5d", "group": "price", "enabled": True},
                    {"name": "trend_score", "group": "technical", "enabled": True},
                    {"name": "news_score", "group": "sentiment", "enabled": True},
                    {"name": "market_trend", "group": "macro", "enabled": True},
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = build_feature_matrix(
        universe=universe,
        prices_dir=prices_dir,
        context=context,
        features=features,
    )

    row = payload["matrix"][0]

    assert payload["rows"] == 1
    assert row["ticker"] == "PRIO3"
    assert row["return_1d"] > 0
    assert row["return_5d"] > 0
    assert row["trend_score"] == 60.0
    assert row["news_score"] == 65.0
    assert row["market_trend"] == "DOWN"


def test_write_feature_matrix_creates_csv(tmp_path: Path):
    universe = tmp_path / "universe.csv"
    prices_dir = tmp_path / "prices"
    context = tmp_path / "context.json"
    features = tmp_path / "features.json"
    output = tmp_path / "matrix.csv"

    prices_dir.mkdir()

    universe.write_text(
        "ticker,sector,last_close,trend_score,momentum_score,volatility_pct,atr_pct,news_score\n"
        "PRIO3,energy,39,60,70,25,3,65\n",
        encoding="utf-8",
    )

    _write_price_file(prices_dir / "PRIO3.SA.csv")
    context.write_text('{"market_trend": "DOWN"}', encoding="utf-8")
    features.write_text(
        '{"features": [{"name": "return_1d", "group": "price", "enabled": true}]}',
        encoding="utf-8",
    )

    payload = write_feature_matrix(
        universe=universe,
        prices_dir=prices_dir,
        context=context,
        features=features,
        output=output,
    )

    assert output.exists()
    assert payload["output"] == str(output)

    with output.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    assert rows[0]["ticker"] == "PRIO3"
    assert "return_1d" in rows[0]
