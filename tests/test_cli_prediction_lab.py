import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from pymercator.cli import build_parser, main


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
            "rolling_majority",
        ]
    )

    assert exit_code == 0
    assert dataset.exists()
    assert evaluation.exists()

    captured = capsys.readouterr()
    assert "PYMERCATOR PREDICTION LAB" in captured.out
    assert "rolling_majority" in captured.out


def test_predict_lab_redirects_default_latest_outputs_to_horizon_dir(
    tmp_path: Path,
    capsys,
):
    matrix = tmp_path / "matrix.csv"
    prices_dir = tmp_path / "prices"
    prediction_dir = tmp_path / "storage" / "prediction"
    dataset = prediction_dir / "latest_dataset.csv"
    evaluation = prediction_dir / "latest_evaluation.json"
    d5_dataset = prediction_dir / "d5" / "latest_dataset.csv"
    d5_evaluation = prediction_dir / "d5" / "latest_evaluation.json"

    prices_dir.mkdir()
    prediction_dir.mkdir(parents=True)
    _write_matrix(matrix)
    _write_price_file(prices_dir / "PRIO3.SA.csv")
    operational_payload = {
        "engine_used": "multi_horizon_ridge",
        "operational": True,
        "experimental": False,
        "horizons": [5, 20, 60],
        "status": "OK",
    }
    evaluation.write_text(json.dumps(operational_payload), encoding="utf-8")

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
            "--horizon",
            "5",
            "--min-train-rows",
            "10",
            "--engines",
            "rolling_majority",
        ]
    )

    assert exit_code == 0
    assert d5_dataset.exists()
    assert d5_evaluation.exists()
    assert not dataset.exists()
    assert json.loads(evaluation.read_text(encoding="utf-8")) == operational_payload
    assert json.loads(d5_evaluation.read_text(encoding="utf-8"))["horizon"] == 5
    assert str(d5_evaluation) in capsys.readouterr().out


def test_predict_evaluate_redirects_default_latest_evaluation_to_horizon_dir(
    tmp_path: Path,
    capsys,
):
    dataset = tmp_path / "dataset.csv"
    prediction_dir = tmp_path / "storage" / "prediction"
    evaluation = prediction_dir / "latest_evaluation.json"
    d20_evaluation = prediction_dir / "d20" / "latest_evaluation.json"
    prediction_dir.mkdir(parents=True)
    dataset.write_text(
        "date,ticker,target_return_20d,target_up_20d\n"
        "2025-01-01,PRIO3,1,1\n"
        "2025-01-02,PRIO3,-1,0\n",
        encoding="utf-8",
    )
    operational_payload = {
        "engine_used": "multi_horizon_ridge",
        "operational": True,
        "experimental": False,
        "horizons": [5, 20, 60],
        "status": "OK",
    }
    evaluation.write_text(json.dumps(operational_payload), encoding="utf-8")

    exit_code = main(
        [
            "predict",
            "evaluate",
            "--dataset",
            str(dataset),
            "--output",
            str(evaluation),
            "--horizon",
            "20",
            "--min-train-rows",
            "1",
            "--engines",
            "rolling_majority",
        ]
    )

    assert exit_code == 0
    assert d20_evaluation.exists()
    assert json.loads(evaluation.read_text(encoding="utf-8")) == operational_payload
    assert json.loads(d20_evaluation.read_text(encoding="utf-8"))["horizon"] == 20
    assert str(d20_evaluation) in capsys.readouterr().out


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


def test_predict_lab_command_rejects_sklearn_as_engine(
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
            "sklearn",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert "ERROR: Unknown prediction engines: sklearn" in captured.err
    assert "Valid engines:" in captured.err
    assert "extratrees" in captured.err
    assert "Baselines:" in captured.err


def test_predict_lab_help_lists_valid_engines(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["predict", "lab", "--help"])

    assert exc_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "Prediction engines to run. Valid engines:" in help_text
    assert "rolling_majority" in help_text
    assert "extratrees" in help_text
    assert "randomforest" in help_text
    assert "gradientboosting" in help_text
    assert "ridge_ensemble" in help_text
    assert "ridge_arbiter" not in help_text
    assert "Prediction horizon in trading days. Default: 5" in help_text
    assert "Parallel workers. Default: 4" in help_text
    assert "Minimum price history. Default: 20" in help_text
    assert "Minimum training rows. Default: 100" in help_text


def test_predict_lab_parser_uses_operational_defaults():
    args = build_parser().parse_args(
        [
            "predict",
            "lab",
            "--matrix",
            "matrix.csv",
            "--prices-dir",
            "prices",
            "--dataset-output",
            "dataset.csv",
            "--evaluation-output",
            "evaluation.json",
        ]
    )

    assert args.horizon == 5
    assert args.n_jobs == 4
    assert args.min_history == 20
    assert args.min_train_rows == 100

    override_args = build_parser().parse_args(
        [
            "predict",
            "lab",
            "--matrix",
            "matrix.csv",
            "--prices-dir",
            "prices",
            "--dataset-output",
            "dataset.csv",
            "--evaluation-output",
            "evaluation.json",
            "--horizon",
            "7",
            "--n-jobs",
            "2",
            "--min-history",
            "30",
            "--min-train-rows",
            "120",
        ]
    )

    assert override_args.horizon == 7
    assert override_args.n_jobs == 2
    assert override_args.min_history == 30
    assert override_args.min_train_rows == 120
