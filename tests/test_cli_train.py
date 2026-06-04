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

    def rich_metrics(accuracy: float, observations: int = 1) -> dict[str, object]:
        return {
            "observations": observations,
            "accuracy": accuracy,
            "precision": 0.56,
            "recall": 0.57,
            "mae_return": 0.018,
            "target_up_rate": 0.52,
            "predicted_up_rate": 0.49,
            "true_positive": 7,
            "true_negative": 6,
            "false_positive": 3,
            "false_negative": 2,
            "false_positive_rate": 0.3333,
            "false_negative_rate": 0.2222,
            "TP": 7,
            "TN": 6,
            "FP": 3,
            "FN": 2,
            "confusion_matrix": {"TP": 7, "TN": 6, "FP": 3, "FN": 2},
            "quality_status": "OK",
            "optimal_threshold": 0.51,
            "calibrated_probability_stats": {
                "mean": 0.51,
                "std": 0.015,
                "p05": 0.48,
                "p50": 0.51,
                "p95": 0.54,
            },
            "probability_distribution": {
                "0.0-0.1": 0,
                "0.1-0.2": 0,
                "0.2-0.3": 0,
                "0.3-0.4": 0,
                "0.4-0.5": 3,
                "0.5-0.6": 6,
                "0.6-0.7": 0,
                "0.7-0.8": 0,
                "0.8-0.9": 0,
                "0.9-1.0": 0,
            },
            "fit_time_seconds": 0.12,
            "predict_time_seconds": 0.03,
        }

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
                        "rolling_majority": rich_metrics(0.5)
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
            ensemble_metrics = rich_metrics(0.57)
            reason = "one or more base engines failed"
        else:
            valid_base_engines = base_engines
            failed_engines = []
            ensemble_metrics = rich_metrics(accuracy_by_horizon.get(horizon, 0.6))
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
                engine: rich_metrics(0.55)
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
    assert payload["schema_version"] == "prediction_evaluation.v1"
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
    assert payload["horizon_observer"]["horizon_scores"] == {
        "D5": 61.0,
        "D20": 64.0,
        "D60": 67.0,
    }
    assert payload["horizon_observer"]["horizon_spread"] == 6.0
    assert payload["horizon_observer"]["horizon_alignment"] == "ALIGNED_STRONG"
    assert payload["horizon_observer"]["dominance_strength"] == "WEAK"
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
    assert evaluation_payload["schema_version"] == "prediction_evaluation.v1"
    assert evaluation_payload["engine_used"] == "multi_horizon_ridge"
    assert evaluation_payload["operational"] is True
    assert evaluation_payload["experimental"] is False
    assert evaluation_payload["trained_models"] == ["multi_horizon_ridge"]
    assert evaluation_payload["horizons"] == [5, 20, 60]
    assert "horizon" not in evaluation_payload
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


def test_cli_train_details_prints_operational_report_and_writes_plain_output(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    import pymercator.cli_train as train_mod
    from pymercator.ui import strip_ansi

    matrix, prices_dir, dataset, evaluation = _write_train_inputs(tmp_path)
    detail_report = tmp_path / "latest_train_detail_report.txt"
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
            "--details",
            "--output",
            str(detail_report),
            "--color",
            "always",
        ]
    )

    assert exit_code == 0
    raw_output = capsys.readouterr().out
    output = strip_ansi(raw_output)
    assert "\x1b[" in raw_output
    assert "PYMERCATOR TRAIN DETAIL" in output
    assert "GLOBAL SUMMARY" in output
    assert "engine" in output
    assert "multi_horizon_ridge" in output
    assert "quality" in output
    assert "edge" in output
    for horizon in ("D5", "D20", "D60"):
        assert horizon in output

    assert "HORIZON SCOREBOARD" in output
    assert "RIDGE WEIGHTS" in output
    assert "PROBABILITY PROFILE" in output
    assert "CONFUSION SUMMARY" in output
    assert output.splitlines().count("OBSERVER") == 1
    assert "VERDICT" in output

    assert "HORIZON OBSERVER" not in output
    assert "BASE ENGINE METRICS" not in output
    assert "RIDGE RESPONSE" not in output
    assert "ridge_coefficients" not in output
    assert "probability_distribution" not in output
    assert "0.5-0.6=6" not in output

    assert "D5 score" in output
    assert "D20 score" in output
    assert "D60 score" in output
    assert "combined_score" in output
    assert "dominant" in output
    assert "behavior" in output

    text = detail_report.read_text(encoding="utf-8")
    assert "\x1b[" not in text
    assert "PYMERCATOR TRAIN DETAIL" in text
    assert "HORIZON SCOREBOARD" in text
    assert "BASE ENGINE METRICS" not in text
    assert "probability_distribution" not in text
    assert json.loads(evaluation.read_text(encoding="utf-8"))["engine_used"] == (
        "multi_horizon_ridge"
    )


def test_cli_train_details_prob_dist_prints_probability_buckets(
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
            "--details",
            "--prob-dist",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "PROBABILITY DISTRIBUTION" in output
    assert "probability_distribution" in output
    assert "0.5-0.6=6" in output
    assert "BASE ENGINE METRICS" not in output


def test_cli_train_details_with_engine_values_stays_summary_only(
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
            "--details",
            "--engines",
            "extratrees,randomforest,gradientboosting",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "GLOBAL SUMMARY" in output
    assert "HORIZON SCOREBOARD" in output
    assert "BASE ENGINE METRICS" not in output
    assert calls[0]["base_engines"] == [
        "extratrees",
        "randomforest",
        "gradientboosting",
    ]


def test_cli_train_details_engines_prints_complete_base_engine_metrics(
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
            "--details",
            "--engines",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "BASE ENGINE METRICS" in output
    assert "D5 extratrees" in output
    assert "D5 randomforest" in output
    assert "D5 gradientboosting" in output
    assert "observations" in output
    assert "false_positive_rate" in output
    assert "fit_time_seconds" in output
    assert "probability_distribution" not in output


def test_cli_train_details_full_prints_all_detail_sections(
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
            "--details",
            "--full",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "HORIZON SCOREBOARD" in output
    assert "RIDGE WEIGHTS" in output
    assert "BASE ENGINE METRICS" in output
    assert "PROBABILITY DISTRIBUTION" in output
    assert "RIDGE RESPONSE" in output
    assert "ridge_coefficients" in output
    assert "RIDGE / ENSEMBLE METRICS" in output
    assert "probability_distribution" in output
    assert "0.5-0.6=6" in output
    assert "edge_vs_baseline" in output


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


def test_cli_train_experimental_preserves_default_latest_operational_evaluation(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    import pymercator.cli_train as train_mod

    matrix, prices_dir, _dataset, _evaluation = _write_train_inputs(tmp_path)
    prediction_dir = tmp_path / "storage" / "prediction"
    dataset = prediction_dir / "latest_dataset.csv"
    evaluation = prediction_dir / "latest_evaluation.json"
    evaluation.parent.mkdir(parents=True)
    operational_payload = {
        "engine_used": "multi_horizon_ridge",
        "operational": True,
        "experimental": False,
        "horizons": [5, 20, 60],
        "status": "OK",
    }
    evaluation.write_text(json.dumps(operational_payload), encoding="utf-8")

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
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["evaluation"]["output"] == str(
        prediction_dir / "experimental" / "latest_evaluation.json"
    )
    assert json.loads(evaluation.read_text(encoding="utf-8")) == operational_payload

    experimental_payload = json.loads(
        (prediction_dir / "experimental" / "latest_evaluation.json").read_text(
            encoding="utf-8"
        )
    )
    assert experimental_payload["engine_used"] == "multi_horizon_ridge"
    assert experimental_payload["operational"] is False
    assert experimental_payload["experimental"] is True
    assert experimental_payload["horizons"] == [5, 20]
    assert (prediction_dir / "experimental" / "d5" / "latest_evaluation.json").exists()
    assert (prediction_dir / "experimental" / "d20" / "latest_evaluation.json").exists()


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


def test_cli_train_baseline_preserves_default_latest_operational_evaluation(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    import pymercator.cli_train as train_mod

    matrix, prices_dir, _dataset, _evaluation = _write_train_inputs(tmp_path)
    prediction_dir = tmp_path / "storage" / "prediction"
    dataset = prediction_dir / "latest_dataset.csv"
    evaluation = prediction_dir / "latest_evaluation.json"
    evaluation.parent.mkdir(parents=True)
    operational_payload = {
        "engine_used": "multi_horizon_ridge",
        "operational": True,
        "experimental": False,
        "horizons": [5, 20, 60],
        "status": "OK",
    }
    evaluation.write_text(json.dumps(operational_payload), encoding="utf-8")

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
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "BASELINE"
    assert payload["evaluation"]["output"] == str(
        prediction_dir / "baseline" / "latest_evaluation.json"
    )
    assert json.loads(evaluation.read_text(encoding="utf-8")) == operational_payload

    baseline_payload = json.loads(
        (prediction_dir / "baseline" / "latest_evaluation.json").read_text(
            encoding="utf-8"
        )
    )
    assert baseline_payload["engine_used"] == "rolling_majority"
    assert baseline_payload["is_baseline"] is True
    assert baseline_payload["status"] == "BASELINE"


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
            "--engines",
            "extratrees,randomforest",
            "--weights",
            "D5=0.2,D10=0.3,D20=0.5",
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
