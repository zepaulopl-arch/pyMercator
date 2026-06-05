import csv
import os
from datetime import date, timedelta
from pathlib import Path

import pytest

from pymercator.legacy_prediction_engines import (
    apply_consensus_guard,
    parse_legacy_engines,
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
        engines=["rolling_majority"],
    )

    assert payload["rows"] > 0
    assert payload["evaluated_rows"] > 0
    assert "rolling_majority" in payload["models"]
    assert payload["engine_status"]["rolling_majority"] == "BASELINE"
    assert payload["engine_used"] == "rolling_majority"
    assert payload["is_baseline"] is True
    assert payload["trained_models"] == []
    assert payload["status"] == "BASELINE"


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
        engines=["rolling_majority"],
    )

    assert payload["status"] == "BASELINE"
    assert dataset.exists()
    assert evaluation.exists()
    assert payload["evaluation"]["evaluated_rows"] > 0
    assert payload["evaluation"]["engine_used"] == "rolling_majority"
    assert payload["evaluation"]["is_baseline"] is True
    assert payload["summary"]["status"] == "BASELINE"
    assert payload["summary"]["engine_count"] == 1


def test_ridge_ensemble_trains_three_base_engines(
    tmp_path: Path,
    monkeypatch,
):
    import pymercator.legacy_prediction_engines as engines_mod

    class DummyModel:
        def __init__(self, value: float):
            self.value = value

        def fit(self, _x_rows, _y_values):
            return None

        def predict(self, x_rows):
            return [self.value for _row in x_rows]

    def fake_make_model(engine, _params, *, n_jobs=4):
        values = {
            "extratrees": 0.10,
            "randomforest": 0.20,
            "gradientboosting": 0.30,
        }
        return DummyModel(values[engine])

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
    monkeypatch.setattr(engines_mod, "_make_model", fake_make_model)

    payload = walk_forward_evaluate(
        dataset=dataset,
        horizon=5,
        min_train_rows=10,
        engines=["ridge_ensemble"],
    )

    assert payload["status"] == "OK"
    assert payload["engine_used"] == "ridge_ensemble"
    assert payload["is_baseline"] is False
    assert payload["base_engines"] == ["extratrees", "randomforest", "gradientboosting"]
    assert payload["valid_base_engines"] == ["extratrees", "randomforest", "gradientboosting"]
    assert payload["failed_engines"] == []
    assert payload["meta_model"] == "ridge"
    assert set(payload["base_metrics"]) == {"extratrees", "randomforest", "gradientboosting"}
    assert payload["ensemble_metrics"]["observations"] > 0
    assert set(payload["ridge_coefficients"]["weights"]) == {
        "extratrees",
        "randomforest",
        "gradientboosting",
    }


def test_ridge_ensemble_degrades_when_one_base_engine_fails(
    tmp_path: Path,
    monkeypatch,
):
    import pymercator.legacy_prediction_engines as engines_mod

    class DummyModel:
        def __init__(self, value: float):
            self.value = value

        def fit(self, _x_rows, _y_values):
            return None

        def predict(self, x_rows):
            return [self.value for _row in x_rows]

    def fake_make_model(engine, _params, *, n_jobs=4):
        if engine == "gradientboosting":
            return None
        return DummyModel(0.10 if engine == "extratrees" else 0.20)

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
    monkeypatch.setattr(engines_mod, "_make_model", fake_make_model)

    payload = walk_forward_evaluate(
        dataset=dataset,
        horizon=5,
        min_train_rows=10,
        engines=["ridge_ensemble"],
    )

    assert payload["status"] == "DEGRADED"
    assert payload["engine_status"]["ridge_ensemble"] == "DEGRADED"
    assert payload["failed_engines"] == ["gradientboosting"]
    assert payload["valid_base_engines"] == ["extratrees", "randomforest"]


def test_ridge_ensemble_fails_with_only_one_base_engine(
    tmp_path: Path,
    monkeypatch,
):
    import pymercator.legacy_prediction_engines as engines_mod

    class DummyModel:
        def fit(self, _x_rows, _y_values):
            return None

        def predict(self, x_rows):
            return [0.10 for _row in x_rows]

    def fake_make_model(engine, _params, *, n_jobs=4):
        return DummyModel() if engine == "extratrees" else None

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
    monkeypatch.setattr(engines_mod, "_make_model", fake_make_model)

    payload = walk_forward_evaluate(
        dataset=dataset,
        horizon=5,
        min_train_rows=10,
        engines=["ridge_ensemble"],
    )

    assert payload["status"] == "FAIL"
    assert payload["engine_status"]["ridge_ensemble"] == "FAIL"
    assert payload["reason"] == "ridge_ensemble requires at least 2 base engines"
    assert payload["valid_base_engines"] == ["extratrees"]


def test_apply_consensus_guard_replaces_outlier_values():
    predictions = {"extratrees": 10.0, "randomforest": 4.5, "gradientboosting": 4.3}
    guarded = apply_consensus_guard(predictions)

    assert guarded["extratrees"] == 4.5
    assert guarded["randomforest"] == 4.5
    assert guarded["gradientboosting"] == 4.3


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
    assert payload["engine_used"] == "ridge_ensemble"
    assert "ridge_ensemble" in payload["models"]



def test_available_engines_exposes_legacy_engines():
    from pymercator.prediction_lab import available_engines

    engines = available_engines()

    assert "rolling_majority" in engines
    assert "extratrees" in engines
    assert "randomforest" in engines
    assert "gradientboosting" in engines
    assert "histgradientboosting" in engines
    assert "logistic_elasticnet" in engines
    assert "sgd_logloss_calibrated" in engines
    assert "adaboost" in engines
    assert "ridge_ensemble" in engines
    assert "sklearn" not in engines


def test_modern_sklearn_engines_use_scaling_and_calibration():
    import pymercator.legacy_prediction_engines as engines_mod

    if not engines_mod.SKLEARN_AVAILABLE:
        pytest.skip("sklearn not available")

    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    logistic = engines_mod._make_classifier(
        "logistic_elasticnet",
        engines_mod._engine_defaults("logistic_elasticnet"),
    )
    assert isinstance(logistic, Pipeline)
    assert isinstance(logistic.named_steps["scaler"], StandardScaler)
    assert logistic.named_steps["model"].penalty == "elasticnet"

    sgd = engines_mod._make_classifier(
        "sgd_logloss_calibrated",
        engines_mod._engine_defaults("sgd_logloss_calibrated"),
    )
    assert isinstance(sgd, Pipeline)
    assert isinstance(sgd.named_steps["scaler"], StandardScaler)
    assert sgd.named_steps["model"].loss == "log_loss"

    return_model = engines_mod._make_model(
        "sgd_logloss_calibrated",
        engines_mod._engine_defaults("sgd_logloss_calibrated"),
    )
    assert isinstance(return_model, engines_mod.ProbabilityReturnAdapter)
    assert return_model.calibrated is True
    assert isinstance(return_model.classifier, Pipeline)

    rows = []
    for index in range(8):
        rows.append(
            {
                "return_1d": index / 100,
                "return_5d": index / 50,
                "return_20d": index / 25,
                "volatility_20d": 0.1,
                "atr_pct": 0.03,
                "trend_score": 60 if index % 2 else 40,
                "momentum_score": 58 if index % 2 else 42,
                "news_score": 55,
                "market_trend": "UP",
                "market_volatility": "NORMAL",
                "target_up_5d": 1 if index % 2 else 0,
            }
        )
    calibrated, meta = engines_mod.fit_calibrated_legacy_classifier(
        "sgd_logloss_calibrated",
        rows,
        "target_up_5d",
        params=engines_mod._engine_defaults("sgd_logloss_calibrated"),
        calibration={"enabled": True, "method": "sigmoid", "cv": 2},
        n_jobs=1,
    )
    assert meta["status"] == "OK"
    assert isinstance(calibrated, CalibratedClassifierCV)


def test_sklearn_library_name_is_not_a_prediction_engine():
    with pytest.raises(ValueError) as exc_info:
        parse_legacy_engines(["sklearn"])

    message = str(exc_info.value)
    assert "Unknown prediction engines: sklearn" in message
    assert "Valid engines:" in message
    assert "extratrees" in message
