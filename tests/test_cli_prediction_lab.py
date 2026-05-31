import json
from datetime import date, timedelta
from pathlib import Path

import pytest

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
            "--engines",
            "rolling_majority,momentum_rule",
        ]
    )

    assert exit_code == 0
    assert dataset.exists()
    assert evaluation.exists()

    captured = capsys.readouterr()
    assert "PYMERCATOR PREDICTION LAB" in captured.out
    assert "rolling_majority" in captured.out


def test_predict_lab_command_accepts_extratrees_engine(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    import pymercator.legacy_prediction_engines as engines_mod

    class FakeExtraTreesRegressor:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def fit(self, _x_rows, _y_values):
            return None

        def predict(self, x_rows):
            return [0.1 for _row in x_rows]

    matrix = tmp_path / "matrix.csv"
    prices_dir = tmp_path / "prices"
    dataset = tmp_path / "dataset.csv"
    evaluation = tmp_path / "evaluation.json"

    prices_dir.mkdir()
    _write_matrix(matrix)
    _write_price_file(prices_dir / "PRIO3.SA.csv")
    monkeypatch.setattr(engines_mod, "SKLEARN_AVAILABLE", True)
    monkeypatch.setattr(engines_mod, "ExtraTreesRegressor", FakeExtraTreesRegressor)

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
            "--engines",
            "extratrees",
            "--n-jobs",
            "4",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Unknown prediction engines" not in captured.err
    assert "extratrees" in captured.out
    payload = json.loads(evaluation.read_text(encoding="utf-8"))
    assert payload["engine_used"] == "extratrees"
    assert payload["is_baseline"] is False
    assert payload["trained_models"] == ["extratrees"]


def test_predict_lab_command_accepts_rolling_majority_engine(
    tmp_path: Path,
    capsys,
):
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
            "--engines",
            "rolling_majority",
        ]
    )

    assert exit_code == 0
    assert "rolling_majority" in capsys.readouterr().out
    payload = json.loads(evaluation.read_text(encoding="utf-8"))
    assert payload["engine_used"] == "rolling_majority"
    assert payload["is_baseline"] is True


def test_predict_lab_command_rejects_unknown_engine_with_valid_list(
    tmp_path: Path,
    capsys,
):
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
            "--engines",
            "sklearn_fake",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert "ERROR: Unknown prediction engines: sklearn_fake" in captured.err
    assert "Valid engines:" in captured.err
    assert "extratrees" in captured.err


def test_predict_lab_help_lists_valid_engines(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["predict", "lab", "--help"])

    assert exc_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "Prediction engines to run. Valid engines:" in help_text
    assert "rolling_majority" in help_text
    assert "extratrees" in help_text
    assert "ridge_arbiter" in help_text
