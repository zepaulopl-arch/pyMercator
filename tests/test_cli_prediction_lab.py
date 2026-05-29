from datetime import date, timedelta
from pathlib import Path

from pymercator.cli import main


def _write_price_file(path: Path, start: float = 10.0) -> None:
    lines = ["date,open,high,low,close,volume"]

    for index in range(80):
        day = (date(2025, 1, 2) + timedelta(days=index)).isoformat()
        close = start + index * 0.2
        lines.append(f"{day},{close},{close},{close},{close},1000")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_matrix(path: Path) -> None:
    path.write_text(
        "ticker,sector,return_1d,return_5d,return_20d,volatility_20d,atr_pct,"
        "trend_score,momentum_score,news_score,market_trend,market_volatility\n"
        "PRIO3,energy,1,5,20,25,3,60,70,65,DOWN,NORMAL\n",
        encoding="utf-8",
    )


def test_predict_lab_command_creates_outputs(tmp_path: Path, capsys):
    matrix = tmp_path / "matrix.csv"
    prices_dir = tmp_path / "prices"
    dataset = tmp_path / "dataset.csv"
    evaluation = tmp_path / "evaluation.json"

    prices_dir.mkdir()
    _write_matrix(matrix)
    _write_price_file(prices_dir / "PRIO3.SA.csv")

    exit_code = main(
        [
            "predict",
            "lab",
            "--matrix",
            str(matrix),
            "--prices-dir",
            str(prices_dir),
            "--dataset-output",
            str(dataset),
            "--evaluation-output",
            str(evaluation),
            "--min-train-rows",
            "10",
        ]
    )

    assert exit_code == 0
    assert dataset.exists()
    assert evaluation.exists()

    captured = capsys.readouterr()
    assert "PYMERCATOR PREDICTION LAB" in captured.out
    assert "rolling_majority" in captured.out
