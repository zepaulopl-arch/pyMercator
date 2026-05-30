import csv
import os
from datetime import date, timedelta
from pathlib import Path

import pytest

from pymercator.legacy_prediction_engines import (
    apply_consensus_guard,
    predict_legacy_engine,
)
from pymercator.prediction_lab import (
    build_prediction_dataset,
    run_prediction_lab,
    walk_forward_evaluate,
    write_prediction_dataset,
)


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


def test_build_prediction_dataset_creates_targets(tmp_path: Path):
    matrix = tmp_path / "matrix.csv"
    prices_dir = tmp_path / "prices"

    prices_dir.mkdir()
    _write_matrix(matrix)
    _write_price_file(prices_dir / "PRIO3.SA.csv")

    payload = build_prediction_dataset(
        matrix=matrix,
        prices_dir=prices_dir,
        horizon=5,
        min_history=20,
    )

    assert payload["rows"] > 0
    assert payload["missing_price_files_count"] == 0

    row = payload["dataset"][0]

    assert "target_return_5d" in row
    assert "target_up_5d" in row
    assert row["ticker"] == "PRIO3"


def test_write_prediction_dataset_creates_csv(tmp_path: Path):
    matrix = tmp_path / "matrix.csv"
    prices_dir = tmp_path / "prices"
    output = tmp_path / "dataset.csv"

    prices_dir.mkdir()
    _write_matrix(matrix)
    _write_price_file(prices_dir / "PRIO3.SA.csv")

    payload = write_prediction_dataset(
        matrix=matrix,
        prices_dir=prices_dir,
        output=output,
        horizon=5,
        min_history=20,
    )

    assert output.exists()
    assert payload["rows"] > 0

    with output.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    assert rows[0]["ticker"] == "PRIO3"


def test_walk_forward_evaluate_returns_baseline_metrics(tmp_path: Path):
    matrix = tmp_path / "matrix.csv"
    prices_dir = tmp_path / "prices"
    dataset = tmp_path / "dataset.csv"

    prices_dir.mkdir()
    _write_matrix(matrix)
    _write_price_file(prices_dir / "PRIO3.SA.csv")

    write_prediction_dataset(
        matrix=matrix,
        prices_dir=prices_dir,
        output=dataset,
        horizon=5,
        min_history=20,
    )

    payload = walk_forward_evaluate(
        dataset=dataset,
        horizon=5,
        min_train_rows=10,
        engines=["rolling_majority", "momentum_rule"],
    )

    assert payload["rows"] > 0
    assert payload["evaluated_rows"] > 0
    assert "rolling_majority" in payload["models"]
    assert "momentum_rule" in payload["models"]


def test_run_prediction_lab_creates_dataset_and_evaluation(tmp_path: Path):
    matrix = tmp_path / "matrix.csv"
    prices_dir = tmp_path / "prices"
    dataset = tmp_path / "dataset.csv"
    evaluation = tmp_path / "evaluation.json"

    prices_dir.mkdir()
    _write_matrix(matrix)
    _write_price_file(prices_dir / "PRIO3.SA.csv")

    payload = run_prediction_lab(
        matrix=matrix,
        prices_dir=prices_dir,
        dataset_output=dataset,
        evaluation_output=evaluation,
        horizon=5,
        min_history=20,
        min_train_rows=10,
        engines=["rolling_majority", "momentum_rule"],
    )

    assert payload["status"] == "OK"
    assert dataset.exists()
    assert evaluation.exists()
    assert payload["evaluation"]["evaluated_rows"] > 0
    assert payload["summary"]["status"] == "OK"
    assert payload["summary"]["engine_count"] == 2


def test_apply_consensus_guard_replaces_outlier_values():
    predictions = {"xgb": 4.5, "catboost": 4.3, "extratrees": 10.0}
    guarded = apply_consensus_guard(predictions)

    assert guarded["extratrees"] == 4.5
    assert guarded["xgb"] == 4.5
    assert guarded["catboost"] == 4.3


def test_predict_legacy_engine_clips_excessive_returns():
    class DummyModel:
        def predict(self, _rows):
            return [100.0]

    value = predict_legacy_engine(DummyModel(), {})
    assert value == 20.0


@pytest.mark.skipif(
    os.environ.get("PYMERCATOR_RUN_ENGINE_TESTS") != "1",
    reason="heavy legacy engine test; set PYMERCATOR_RUN_ENGINE_TESTS=1 to run",
)
def test_walk_forward_evaluate_runs_all_engines(tmp_path: Path):
    matrix = tmp_path / "matrix.csv"
    prices_dir = tmp_path / "prices"
    dataset = tmp_path / "dataset.csv"

    prices_dir.mkdir()
    _write_matrix(matrix)
    _write_price_file(prices_dir / "PRIO3.SA.csv")

    write_prediction_dataset(
        matrix=matrix,
        prices_dir=prices_dir,
        output=dataset,
        horizon=5,
        min_history=20,
    )

    payload = walk_forward_evaluate(
        dataset=dataset,
        horizon=5,
        min_train_rows=10,
    )

    assert payload["evaluated_rows"] > 0
    assert "rolling_majority" in payload["models"]
    assert "momentum_rule" in payload["models"]



def test_available_engines_exposes_legacy_engines():
    from pymercator.prediction_lab import available_engines

    engines = available_engines()

    assert "xgb" in engines
    assert "catboost" in engines
    assert "extratrees" in engines
    assert "ridge_arbiter" in engines
