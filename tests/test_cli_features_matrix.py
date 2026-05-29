import json
from datetime import date, timedelta
from pathlib import Path

from pymercator.cli import main


def _write_price_file(path: Path) -> None:
    lines = ["date,open,high,low,close,volume"]

    for index in range(30):
        day = (date(2025, 1, 2) + timedelta(days=index)).isoformat()
        close = 10.0 + index
        lines.append(f"{day},{close},{close},{close},{close},1000")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_features_matrix_command_creates_output(tmp_path: Path, capsys):
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
                    {"name": "news_score", "group": "sentiment", "enabled": True},
                    {"name": "market_trend", "group": "macro", "enabled": True},
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "features",
            "matrix",
            "--universe",
            str(universe),
            "--prices-dir",
            str(prices_dir),
            "--context",
            str(context),
            "--features",
            str(features),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert output.exists()

    captured = capsys.readouterr()
    assert "PYMERCATOR FEATURE MATRIX" in captured.out
    assert "ROWS" in captured.out
