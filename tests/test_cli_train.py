import json
from pathlib import Path

import pytest

from pymercator.cli import build_parser, main

BASE_ENGINES = ["extratrees", "randomforest", "gradientboosting"]


def _write_train_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    matrix = tmp_path / "matrix.csv"
    prices_dir = tmp_path / "prices"
    dataset = tmp_path / "dataset.csv"
    evaluation = tmp_path / "evaluation.json"
    matrix.write_text("ticker,sector,return_1d\nPRIO3,OilGas,1\n", encoding="utf-8")
    prices_dir.mkdir()
    return matrix, prices_dir, dataset, evaluation


def _fake_lab_factory(
    calls: list[dict],
    *,
    status_by_horizon: dict[int, str] | None = None,
    accuracy_by_horizon: dict[int, float] | None = None,
):
    status_by_horizon = status_by_horizon or {}
    accuracy_by_horizon = accuracy_by_horizon or {5: 0.61, 20: 0.64, 60: 0.67}

    def fake_lab(**kwargs):
        calls.append(dict(kwargs))
        dataset_output = Path(kwargs["dataset_output"])
        evaluation_output = Path(kwargs["evaluation_output"])
        dataset_output.parent.mkdir(parents=True, exist_ok=True)
        evaluation_output.parent.mkdir(parents=True, exist_ok=True)
        dataset_output.write_text(
            "date,ticker\n2025-01-01,PRIO3\n2025-01-02,PRIO3\n",
            encoding="utf-8",
        )

        if kwargs["engines"] == ["rolling_majority"]:
            payload = {
                "dataset": {"rows": 2, "output": str(dataset_output)},
                "evaluation": {
                    "rows": 2,
                    "evaluated_rows": 1,
                    "engines": ["rolling_majority"],
                    "engine_status": {"rolling_majority": "BASELINE"},
                    "engine_used": "rolling_majority",
                    "is_baseline": True,
                    "models": {
                        "rolling_majority": {"accuracy": 0.5, "observations": 1}
                    },
                    "output": str(evaluation_output),
                },
            }
            evaluation_output.write_text(json.dumps(payload["evaluation"]), encoding="utf-8")
            return payload

        horizon = int(kwargs["horizon"])
        status = status_by_horizon.get(horizon, "OK")
        base_engines = list(kwargs.get("base_engines") or BASE_ENGINES)
        if status == "FAIL":
            valid_base_engines = base_engines[:1]
            failed_engines = base_engines[1:]
            ensemble_metrics = {}
            reason = "ridge_ensemble requires at least 2 base engines"
        elif status == "DEGRADED":
            valid_base_engines = base_engines[:2]
            failed_engines = base_engines[2:]
            ensemble_metrics = {"accuracy": 0.57, "observations": 1}
            reason = "one or more base engines failed"
        else:
            valid_base_engines = base_engines
            failed_engines = []
            ensemble_metrics = {
                "accuracy": accuracy_by_horizon.get(horizon, 0.6),
                "observations": 1,
            }
            reason = ""

        weights = (
            {engine: round(1.0 / len(valid_base_engines), 4) for engine in valid_base_engines}
            if len(valid_base_engines) >= 2
            else {}
        )
        evaluation = {
            "rows": 2,
            "evaluated_rows": 1,
            "engines": kwargs["engines"],
            "status": status,
            "reason": reason,
            "engine_status": {"ridge_ensemble": status},
            "engine_used": "ridge_ensemble",
            "is_baseline": False,
            "base_engines": base_engines,
            "valid_base_engines": valid_base_engines,
            "failed_engines": failed_engines,
            "meta_model": "ridge",
            "base_metrics": {
                engine: {"accuracy": 0.55, "observations": 1}
                for engine in valid_base_engines
            },
            "ensemble_metrics": ensemble_metrics,
            "ridge_coefficients": {"intercept": 0.0, "weights": weights},
            "models": {"ridge_ensemble": ensemble_metrics},
            "output": str(evaluation_output),
        }
        evaluation_output.write_text(json.dumps(evaluation), encoding="utf-8")
        return {
            "dataset": {"rows": 2, "output": str(dataset_output)},
            "evaluation": evaluation,
        }

    return fake_lab


def test_cli_train_generates_multi_horizon_evaluation_by_default(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    import pymercator.cli_train as train_mod

    matrix, prices_dir, dataset, evaluation = _write_train_inputs(tmp_path)
    calls: list[dict] = []
    monkeypatch.setattr(train_mod, "run_prediction_lab", _fake_lab_factory(calls))

    exit_code = main(
        [
            "train",
            "--matrix",
            str(matrix),
            "--prices-dir",
            str(prices_dir),
            "--dataset-output",
            str(dataset),
            "--evaluation-output",
            str(evaluation),
            "--min-train-rows",
            "2",
            "--json",
        ]
    )

    assert exit_code == 0
    assert [call["horizon"] for call in calls] == [5, 20, 60]
    assert [call["engines"] for call in calls] == [["ridge_ensemble"]] * 3
    assert [call["base_engines"] for call in calls] == [BASE_ENGINES] * 3
    assert [call["n_jobs"] for call in calls] == [4, 4, 4]
    assert [call["autotune"] for call in calls] == [False, False, False]

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "OK"
    assert payload["engine_used"] == "multi_horizon_ridge"
    assert payload["is_baseline"] is False
    assert payload["base_engines"] == BASE_ENGINES
    assert payload["meta_model"] == "ridge"
    assert set(payload["horizon_models"]) == {"D5", "D20", "D60"}
    assert payload["horizon_observer"]["mode"] == "weighted"
    assert payload["horizon_observer"]["dominant_horizon"] == "D60"
    assert payload["horizon_observer"]["behavior"] in {
        "TREND_CONFIRM",
        "POSITIONAL_SETUP",
        "SWING",
        "TACTICAL",
        "DIVERGENT",
        "SWING_WAIT",
        "POSITIONAL_EARLY",
        "AVOID",
    }

    evaluation_payload = json.loads(evaluation.read_text(encoding="utf-8"))
    multi_payload = json.loads(
        (evaluation.parent / "latest_multi_horizon_evaluation.json").read_text(
            encoding="utf-8"
        )
    )
    assert evaluation_payload == multi_payload
    assert evaluation_payload["engine_used"] == "multi_horizon_ridge"
    assert evaluation_payload["trained_models"] == ["multi_horizon_ridge"]
    assert evaluation_payload["horizons"] == [5, 20, 60]
    assert evaluation_payload["base_engines"] == BASE_ENGINES
    assert evaluation_payload["meta_model"] == "ridge"
    assert set(evaluation_payload["horizon_models"]) == {"D5", "D20", "D60"}
    assert evaluation_payload["horizon_models"]["D5"]["engine_used"] == "ridge_ensemble"
    assert evaluation_payload["horizon_models"]["D5"]["meta_model"] == "ridge"
    assert "extratrees" != evaluation_payload["engine_used"]
    assert "profile" not in evaluation_payload


def test_cli_train_profile_is_ignored_with_warning(tmp_path: Path, monkeypatch, capsys):
    import pymercator.cli_train as train_mod

    matrix, prices_dir, dataset, evaluation = _write_train_inputs(tmp_path)
    calls: list[dict] = []
    monkeypatch.setattr(train_mod, "run_prediction_lab", _fake_lab_factory(calls))

    exit_code = main(
        [
            "train",
            "--profile",
            "CON",
            "--matrix",
            str(matrix),
            "--prices-dir",
            str(prices_dir),
            "--dataset-output",
            str(dataset),
            "--evaluation-output",
            str(evaluation),
            "--min-train-rows",
            "2",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    evaluation_payload = json.loads(evaluation.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert "WARNING: --profile is ignored by train. Profiles are applied in run." in captured.err
    assert payload["engine_used"] == "multi_horizon_ridge"
    assert "profile" not in payload
    assert "profile" not in evaluation_payload
    assert not (tmp_path / "evaluation_CON.json").exists()


def test_cli_train_blocks_when_matrix_is_missing(tmp_path: Path, capsys):
    prices_dir = tmp_path / "prices"
    prices_dir.mkdir()

    exit_code = main(
        [
            "train",
            "--matrix",
            str(tmp_path / "missing.csv"),
            "--prices-dir",
            str(prices_dir),
            "--json",
        ]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "BLOCKED"
    assert payload["reason"] == "feature matrix not found"


def test_cli_train_parse_engines_keeps_real_names():
    from pymercator.cli_train import parse_engines

    assert parse_engines("extratrees,randomforest") == ["extratrees", "randomforest"]
    assert parse_engines("") == ["ridge_ensemble"]
    assert parse_engines("sklearn") == ["sklearn"]


def test_cli_train_parser_uses_config_driven_defaults():
    args = build_parser().parse_args(["train"])

    assert args.profile == ""
    assert args.horizons == ""
    assert args.horizon is None
    assert args.n_jobs is None
    assert args.min_history is None
    assert args.min_train_rows is None

    override_args = build_parser().parse_args(
        [
            "train",
            "--horizons",
            "7,20",
            "--n-jobs",
            "2",
            "--min-history",
            "30",
            "--min-train-rows",
            "120",
        ]
    )

    assert override_args.horizons == "7,20"
    assert override_args.n_jobs == 2
    assert override_args.min_history == 30
    assert override_args.min_train_rows == 120


def test_cli_train_help_lists_multi_horizon_defaults(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["train", "--help"])

    assert exc_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "Train multi-horizon prediction ensemble. Profile-independent." in help_text
    assert "--profile" not in help_text
    assert "Prediction horizons in trading days. Default: 5,20,60" in help_text
    assert "Base engines for multi_horizon_ridge. Valid:" in help_text
    assert "extratrees" in help_text
    assert "randomforest" in help_text
    assert "gradientboosting" in help_text
    assert "rolling_majority" in help_text
    assert "sklearn" not in help_text
    assert "Minimum price history. Default: 120" in help_text
    assert "Minimum training rows. Default: 100" in help_text
    assert "Parallel workers. Default: 4" in help_text
    assert "Autotune iterations. Default: 20" in help_text
    assert "Autotune CV folds. Default: 3" in help_text


def test_cli_train_overrides_horizons_base_engines_weights_and_autotune(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    import pymercator.cli_train as train_mod

    matrix, prices_dir, dataset, evaluation = _write_train_inputs(tmp_path)
    calls: list[dict] = []
    monkeypatch.setattr(train_mod, "run_prediction_lab", _fake_lab_factory(calls))

    exit_code = main(
        [
            "train",
            "--matrix",
            str(matrix),
            "--prices-dir",
            str(prices_dir),
            "--dataset-output",
            str(dataset),
            "--evaluation-output",
            str(evaluation),
            "--min-train-rows",
            "2",
            "--horizons",
            "5,20",
            "--engines",
            "extratrees,randomforest",
            "--weights",
            "D5=0.2,D20=0.8",
            "--n-jobs",
            "2",
            "--autotune",
            "--autotune-iter",
            "30",
            "--autotune-cv",
            "2",
            "--json",
        ]
    )

    assert exit_code == 0
    assert [call["horizon"] for call in calls] == [5, 20]
    assert [call["base_engines"] for call in calls] == [
        ["extratrees", "randomforest"],
        ["extratrees", "randomforest"],
    ]
    assert [call["n_jobs"] for call in calls] == [2, 2]
    assert [call["autotune"] for call in calls] == [True, True]
    assert [call["autotune_iter"] for call in calls] == [30, 30]
    assert [call["autotune_cv"] for call in calls] == [2, 2]

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "OK"
    assert payload["horizons"] == [5, 20]
    assert payload["base_engines"] == ["extratrees", "randomforest"]
    assert payload["observer"]["weights"] == {"D5": 0.2, "D20": 0.8}
    assert payload["training"]["n_jobs"] == 2
    assert payload["training"]["autotune"] is True
    assert payload["training"]["autotune_iter"] == 30
    assert payload["training"]["autotune_cv"] == 2


def test_cli_train_explicit_rolling_majority_is_baseline(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    import pymercator.cli_train as train_mod

    matrix, prices_dir, dataset, evaluation = _write_train_inputs(tmp_path)
    calls: list[dict] = []
    monkeypatch.setattr(train_mod, "run_prediction_lab", _fake_lab_factory(calls))

    exit_code = main(
        [
            "train",
            "--matrix",
            str(matrix),
            "--prices-dir",
            str(prices_dir),
            "--dataset-output",
            str(dataset),
            "--evaluation-output",
            str(evaluation),
            "--min-train-rows",
            "2",
            "--engines",
            "rolling_majority",
            "--json",
        ]
    )

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0]["engines"] == ["rolling_majority"]
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "BASELINE"
    assert payload["engine_used"] == "rolling_majority"
    assert payload["is_baseline"] is True

    evaluation_payload = json.loads(evaluation.read_text(encoding="utf-8"))
    assert evaluation_payload["engine_used"] == "rolling_majority"
    assert evaluation_payload["is_baseline"] is True
    assert evaluation_payload["status"] == "BASELINE"


def test_cli_train_rejects_sklearn_as_engine(tmp_path: Path, capsys):
    matrix, prices_dir, dataset, evaluation = _write_train_inputs(tmp_path)

    exit_code = main(
        [
            "train",
            "--matrix",
            str(matrix),
            "--prices-dir",
            str(prices_dir),
            "--dataset-output",
            str(dataset),
            "--evaluation-output",
            str(evaluation),
            "--engines",
            "sklearn",
            "--json",
        ]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "FAIL"
    assert "Unknown prediction engines: sklearn" in payload["reason"]
    assert "extratrees" in payload["reason"]
    assert not evaluation.exists()


def test_cli_train_degrades_when_one_horizon_fails(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    import pymercator.cli_train as train_mod

    matrix, prices_dir, dataset, evaluation = _write_train_inputs(tmp_path)
    calls: list[dict] = []
    monkeypatch.setattr(
        train_mod,
        "run_prediction_lab",
        _fake_lab_factory(calls, status_by_horizon={60: "FAIL"}),
    )

    exit_code = main(
        [
            "train",
            "--matrix",
            str(matrix),
            "--prices-dir",
            str(prices_dir),
            "--dataset-output",
            str(dataset),
            "--evaluation-output",
            str(evaluation),
            "--min-train-rows",
            "2",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "DEGRADED"
    assert payload["engine_used"] == "multi_horizon_ridge"
    assert payload["horizon_models"]["D60"]["status"] == "FAIL"
    assert payload["reason"] == "one or more horizons failed or degraded"


def test_cli_train_fails_with_fewer_than_two_valid_horizons(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    import pymercator.cli_train as train_mod

    matrix, prices_dir, dataset, evaluation = _write_train_inputs(tmp_path)
    calls: list[dict] = []
    monkeypatch.setattr(
        train_mod,
        "run_prediction_lab",
        _fake_lab_factory(calls, status_by_horizon={20: "FAIL", 60: "FAIL"}),
    )

    exit_code = main(
        [
            "train",
            "--matrix",
            str(matrix),
            "--prices-dir",
            str(prices_dir),
            "--dataset-output",
            str(dataset),
            "--evaluation-output",
            str(evaluation),
            "--min-train-rows",
            "2",
            "--json",
        ]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "FAIL"
    assert payload["engine_used"] == "multi_horizon_ridge"
    assert payload["reason"] == "multi_horizon_ridge requires at least 2 valid horizons"
