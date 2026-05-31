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
    asset_count: int = 78,
    asset_count_by_horizon: dict[int, int] | None = None,
    status_by_horizon: dict[int, str] | None = None,
    accuracy_by_horizon: dict[int, float] | None = None,
):
    asset_count_by_horizon = asset_count_by_horizon or {}
    status_by_horizon = status_by_horizon or {}
    accuracy_by_horizon = accuracy_by_horizon or {5: 0.61, 20: 0.64, 60: 0.67}

    def fake_lab(**kwargs):
        calls.append(dict(kwargs))
        dataset_output = Path(kwargs["dataset_output"])
        evaluation_output = Path(kwargs["evaluation_output"])
        dataset_output.parent.mkdir(parents=True, exist_ok=True)
        evaluation_output.parent.mkdir(parents=True, exist_ok=True)
        horizon = int(kwargs["horizon"])
        horizon_asset_count = asset_count_by_horizon.get(horizon, asset_count)
        tickers = [f"TCK{index:03d}" for index in range(horizon_asset_count)]
        dataset_output.write_text(
            "date,ticker\n"
            + "\n".join(
                f"2025-01-01,{ticker}\n2025-01-02,{ticker}"
                for ticker in tickers
            )
            + "\n",
            encoding="utf-8",
        )

        if kwargs["engines"] == ["rolling_majority"]:
            payload = {
                "dataset": {
                    "rows": horizon_asset_count * 2,
                    "output": str(dataset_output),
                },
                "evaluation": {
                    "rows": horizon_asset_count * 2,
                    "evaluated_rows": horizon_asset_count,
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
            "rows": horizon_asset_count * 2,
            "evaluated_rows": horizon_asset_count,
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
            "dataset": {
                "rows": horizon_asset_count * 2,
                "output": str(dataset_output),
            },
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
    assert payload["operational"] is True
    assert payload["experimental"] is False
    assert payload["dataset"]["assets"] == 78
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
    assert evaluation_payload["operational"] is True
    assert evaluation_payload["experimental"] is False
    assert evaluation_payload["trained_models"] == ["multi_horizon_ridge"]
    assert evaluation_payload["horizons"] == [5, 20, 60]
    assert evaluation_payload["base_engines"] == BASE_ENGINES
    assert evaluation_payload["meta_model"] == "ridge"
    assert evaluation_payload["row_count_by_horizon"] == {"D5": 156, "D20": 156, "D60": 156}
    assert evaluation_payload["asset_count_by_horizon"] == {"D5": 78, "D20": 78, "D60": 78}
    assert evaluation_payload["model_quality"]["status"] in {"OK", "STRONG"}
    assert "ensemble_accuracy" in evaluation_payload["model_quality"]
    assert "dropped_assets_by_horizon" in evaluation_payload
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


def test_cli_train_lists_dropped_assets_by_horizon_with_reason(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    import pymercator.cli_train as train_mod

    universe = tmp_path / "universe.csv"
    matrix = tmp_path / "matrix.csv"
    prices_dir = tmp_path / "prices"
    dataset = tmp_path / "dataset.csv"
    evaluation = tmp_path / "evaluation.json"
    prices_dir.mkdir()
    tickers = [f"TCK{index:03d}" for index in range(60)]
    universe.write_text(
        "ticker,sector,last_close,trend_score,momentum_score,volatility_pct,atr_pct,news_score\n"
        + "\n".join(
            f"{ticker},energy,10,60,60,10,2,60" for ticker in tickers
        )
        + "\n",
        encoding="utf-8",
    )
    matrix.write_text(
        "ticker,sector,return_1d\n"
        + "\n".join(f"{ticker},energy,1" for ticker in tickers)
        + "\n",
        encoding="utf-8",
    )
    for ticker in tickers:
        row_count = 170 if ticker == "TCK059" else 220
        rows = ["date,open,high,low,close,volume"]
        rows.extend(
            f"2025-01-{(index % 28) + 1:02d},10,10,10,10,1000"
            for index in range(row_count)
        )
        (prices_dir / f"{ticker}.SA.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")

    calls: list[dict] = []
    monkeypatch.setattr(
        train_mod,
        "run_prediction_lab",
        _fake_lab_factory(
            calls,
            asset_count=60,
            asset_count_by_horizon={5: 60, 20: 60, 60: 59},
        ),
    )

    exit_code = main(
        [
            "train",
            "--universe",
            str(universe),
            "--matrix",
            str(matrix),
            "--prices-dir",
            str(prices_dir),
            "--dataset-output",
            str(dataset),
            "--evaluation-output",
            str(evaluation),
            "--min-history",
            "120",
            "--min-train-rows",
            "2",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    evaluation_payload = json.loads(evaluation.read_text(encoding="utf-8"))
    assert payload["status"] == "OK"
    assert evaluation_payload["asset_count_by_horizon"]["D60"] == 59
    assert evaluation_payload["dropped_assets_by_horizon"]["D5"] == []
    assert evaluation_payload["dropped_assets_by_horizon"]["D20"] == []
    assert evaluation_payload["dropped_assets_by_horizon"]["D60"] == [
        {
            "ticker": "TCK059",
            "reason": "insufficient history for D60: rows=170, required=181",
            "price_rows": 170,
        }
    ]


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
    assert args.experimental is False
    assert args.allow_small_universe is False

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


def test_cli_train_experimental_overrides_horizons_base_engines_weights_and_autotune(
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
            "--experimental",
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
    assert payload["experimental"] is True
    assert payload["operational"] is False
    assert payload["horizons"] == [5, 20]
    assert payload["base_engines"] == ["extratrees", "randomforest"]
    assert payload["observer"]["weights"] == {"D5": 0.2, "D20": 0.8}
    assert payload["training"]["n_jobs"] == 2
    assert payload["training"]["autotune"] is True
    assert payload["training"]["autotune_iter"] == 30
    assert payload["training"]["autotune_cv"] == 2

    evaluation_payload = json.loads(evaluation.read_text(encoding="utf-8"))
    assert evaluation_payload["experimental"] is True
    assert evaluation_payload["operational"] is False
    assert evaluation_payload["autotune"]["enabled"] is True
    assert evaluation_payload["autotune"]["autotune_iter"] == 30
    assert evaluation_payload["autotune"]["autotune_cv"] == 2


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


def test_cli_train_autotune_records_summary_in_operational_json(
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
            "--autotune",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "OK"
    assert [call["autotune"] for call in calls] == [True, True, True]

    evaluation_payload = json.loads(evaluation.read_text(encoding="utf-8"))
    assert evaluation_payload["autotune"]["enabled"] is True
    assert evaluation_payload["autotune"]["autotune_iter"] == 20
    assert evaluation_payload["autotune"]["autotune_cv"] == 3
    assert evaluation_payload["autotune"]["asset_count"] == 78
    assert evaluation_payload["autotune"]["row_count_by_horizon"] == {
        "D5": 156,
        "D20": 156,
        "D60": 156,
    }


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


def test_cli_train_rejects_non_standard_horizons_without_experimental(
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
            "--horizons",
            "5,10,20",
            "--json",
        ]
    )

    assert exit_code == 1
    assert calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "FAIL"
    assert payload["reason"] == (
        "Non-standard horizons require --experimental. "
        "Default operational horizons are D5,D20,D60."
    )
    assert not evaluation.exists()


def test_cli_train_rejects_two_operational_base_engines_without_experimental(
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
            "--engines",
            "extratrees,randomforest",
            "--json",
        ]
    )

    assert exit_code == 1
    assert calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "FAIL"
    assert payload["reason"] == (
        "Operational training requires 3 base engines: "
        "extratrees,randomforest,gradientboosting"
    )
    assert not evaluation.exists()


def test_cli_train_fails_with_insufficient_operational_assets(
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
        _fake_lab_factory(calls, asset_count=1),
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
    assert payload["reason"] == "insufficient assets for operational training"
    assert payload["dataset"]["assets"] == 1
    assert payload["dataset"]["min_assets"] == 30
    assert payload["diagnostic"]["inputs"]["feature_matrix_assets"] == 1
    assert payload["diagnostic"]["dataset_by_horizon"]["D5"]["assets"] == 1
    assert payload["diagnostic"]["bottleneck_step"]

    evaluation_payload = json.loads(evaluation.read_text(encoding="utf-8"))
    assert evaluation_payload["status"] == "FAIL"
    assert evaluation_payload["engine_used"] == "multi_horizon_ridge"
    assert evaluation_payload["status"] != "OK"
    diagnostic_path = evaluation.with_name("latest_failed_training_diagnostic.json")
    assert diagnostic_path.exists()


def test_train_diagnostic_normalizes_b3_ticker_suffixes(tmp_path: Path):
    from pymercator.cli_train import _build_training_diagnostic

    universe = tmp_path / "universe.csv"
    matrix = tmp_path / "matrix.csv"
    prices_dir = tmp_path / "prices"
    prices_dir.mkdir()

    universe.write_text("ticker,sector\nPETR4,energy\n", encoding="utf-8")
    matrix.write_text("ticker,sector\nPETR4,energy\n", encoding="utf-8")
    (prices_dir / "PETR4.SA.csv").write_text(
        "date,close\n2025-01-01,10\n2025-01-02,11\n",
        encoding="utf-8",
    )

    diagnostic = _build_training_diagnostic(
        universe=str(universe),
        matrix=str(matrix),
        prices_dir=str(prices_dir),
        min_history=2,
        min_assets=1,
        row_count_by_horizon={"D5": 1},
        asset_count_by_horizon={"D5": 1},
        dataset_assets_by_horizon={"D5": {"PETR4"}},
    )

    assert diagnostic["inputs"]["universe_assets"] == 1
    assert diagnostic["inputs"]["feature_matrix_assets"] == 1
    assert diagnostic["inputs"]["valid_price_files"] == 1
    assert diagnostic["filter_losses"]["assets_after_join"] == 1


def test_cli_train_fails_when_one_operational_horizon_fails(
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

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "FAIL"
    assert payload["engine_used"] == "multi_horizon_ridge"
    assert payload["horizon_models"]["D60"]["status"] == "FAIL"
    assert payload["reason"] == "insufficient valid base engines for D60"


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
    assert payload["reason"] == "insufficient valid base engines for D20"
