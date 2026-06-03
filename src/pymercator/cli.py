from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pymercator import presets as presets_mod
from pymercator import terminal_ui as ui
from pymercator.cli_context import resolve_market_context_args
from pymercator.ui import (
    format_kv,
    format_kv_section,
    muted_line,
    set_color_mode,
    set_palette,
    set_ui_config_path,
)

DEFAULT_PREDICTION_HORIZON = 5
DEFAULT_PREDICTION_MIN_HISTORY = 20
DEFAULT_PREDICTION_MIN_TRAIN_ROWS = 100
DEFAULT_PREDICTION_N_JOBS = 4
DEFAULT_TRAIN_HORIZONS = "5,20,60"
DEFAULT_TRAIN_MIN_HISTORY = 120
DEFAULT_TRAIN_MIN_TRAIN_ROWS = 100
DEFAULT_TRAIN_N_JOBS = 4
DEFAULT_TRAIN_AUTOTUNE_ITER = 20
DEFAULT_TRAIN_AUTOTUNE_CV = 3
DEFAULT_TRAIN_CALIBRATION_METHOD = "sigmoid"
DEFAULT_TRAIN_CALIBRATION_CV = 3
DEFAULT_TRAIN_THRESHOLD_METRIC = "balanced_accuracy"


class _TrainEnginesAction(argparse.Action):
    def __init__(self, option_strings, dest, **kwargs):
        kwargs["nargs"] = "?"
        super().__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values or "")
        setattr(namespace, "detail_engines", True)


def _run_sentiment_command(args: argparse.Namespace) -> int:
    from pymercator.cli_sentiment import run_sentiment_command

    return run_sentiment_command(args)


def _run_predict_command(args: argparse.Namespace) -> int:
    from pymercator.cli_predict import run_predict_command

    return run_predict_command(args)


def _run_features_command(args: argparse.Namespace) -> int:
    from pymercator.cli_features import run_features_command

    return run_features_command(args)


def _run_indices_command(args: argparse.Namespace) -> int:
    from pymercator.cli_indices import run_indices_command

    return run_indices_command(args)


def _run_execution_command(args: argparse.Namespace) -> int:
    from pymercator.cli_execution import run_execution_command

    return run_execution_command(args)


def _run_confirm_command(args: argparse.Namespace) -> int:
    from pymercator.cli_confirm import run_confirm_command

    return run_confirm_command(args)


def _run_context_command(args: argparse.Namespace) -> int:
    from pymercator.cli_context import run_context_command

    return run_context_command(args)


def _run_legacy_command(args: argparse.Namespace) -> int:
    from pymercator.cli_legacy import run_legacy_command

    return run_legacy_command(args)


def _run_update_command(args: argparse.Namespace) -> int:
    from pymercator.cli_update import run_update_command

    return run_update_command(args)


def _run_train_command(args: argparse.Namespace) -> int:
    from pymercator.cli_train import run_train_command

    return run_train_command(args)


def _run_run_command(args: argparse.Namespace) -> int:
    from pymercator.cli_run import run_run_command

    return run_run_command(args)


def _run_observe_command(args: argparse.Namespace) -> int:
    from pymercator.cli_observe import run_observe_command

    return run_observe_command(args)


def _run_scenario_command(args: argparse.Namespace) -> int:
    from pymercator.cli_scenario import run_scenario_command

    return run_scenario_command(args)


def _parse_csv_arg(value: str) -> list[str]:
    return [
        item.strip()
        for item in str(value or "").split(",")
        if item.strip()
    ]


def _extract_ui_args(argv: list[str] | None) -> tuple[list[str] | None, str, str, str]:
    if argv is None:
        raw = list(sys.argv[1:])
    else:
        raw = list(argv)

    cleaned: list[str] = []
    mode = "auto"
    palette = ""
    ui_config = ""
    index = 0
    while index < len(raw):
        item = raw[index]
        if item == "--no-color":
            mode = "never"
            index += 1
            continue
        if item == "--color":
            if index + 1 >= len(raw):
                cleaned.append(item)
                index += 1
                continue
            mode = raw[index + 1]
            index += 2
            continue
        if item.startswith("--color="):
            mode = item.split("=", 1)[1]
            index += 1
            continue
        if item == "--palette":
            if index + 1 >= len(raw):
                cleaned.append(item)
                index += 1
                continue
            palette = raw[index + 1]
            index += 2
            continue
        if item.startswith("--palette="):
            palette = item.split("=", 1)[1]
            index += 1
            continue
        if item == "--ui-config":
            if index + 1 >= len(raw):
                cleaned.append(item)
                index += 1
                continue
            ui_config = raw[index + 1]
            index += 2
            continue
        if item.startswith("--ui-config="):
            ui_config = item.split("=", 1)[1]
            index += 1
            continue
        cleaned.append(item)
        index += 1

    if mode not in {"auto", "always", "never"}:
        mode = "auto"
    return cleaned, mode, palette, ui_config


def _prediction_engines_help() -> str:
    try:
        from pymercator.legacy_prediction_engines import (
            VALID_PREDICTION_ENGINES,
        )

        valid = ", ".join(VALID_PREDICTION_ENGINES)
    except Exception:
        valid = "rolling_majority, extratrees, randomforest, gradientboosting, ridge_ensemble"

    return f"Prediction engines to run. Valid engines: {valid}"


def _run_short_lab_command(args: argparse.Namespace) -> int:
    profile = presets_mod.resolve_profile(args.profile if getattr(args, "profile", None) else None)
    paths = profile.get("paths", {})
    pred = profile.get("prediction", {})
    fast_profile = presets_mod.resolve_profile("fast")

    engines = pred.get("engines", [])
    if getattr(args, "fast", False):
        engines = fast_profile.get("prediction", {}).get("engines", engines)

    from pymercator.cli_predict import (
        resolve_single_horizon_dataset_output,
        resolve_single_horizon_evaluation_output,
    )
    from pymercator.prediction_lab import render_prediction_lab_summary, run_prediction_lab

    horizon = int(getattr(args, "horizon", 0) or 0)
    if horizon <= 0:
        horizon = int(pred.get("horizon", 5))

    n_jobs = int(getattr(args, "jobs", 0) or 0)
    if n_jobs <= 0:
        n_jobs = int(pred.get("n_jobs", 1))

    payload = run_prediction_lab(
        matrix=paths.get("feature_matrix"),
        prices_dir=paths.get("prices_dir"),
        dataset_output=resolve_single_horizon_dataset_output(
            paths.get("prediction_dataset"),
            horizon,
        ),
        evaluation_output=resolve_single_horizon_evaluation_output(
            paths.get("prediction_evaluation"),
            horizon,
        ),
        horizon=horizon,
        min_history=pred.get("min_history", 20),
        min_train_rows=pred.get("min_train_rows", 100),
        engines=(args.engines.split(",") if getattr(args, "engines", None) else engines),
        n_jobs=max(1, n_jobs),
        autotune=bool(getattr(args, "autotune", False) or pred.get("autotune", False)),
        autotune_iter=pred.get("autotune_iter", 15),
        autotune_cv=pred.get("autotune_cv", 3),
    )

    if getattr(args, "json", False):
        import json as _json

        print(_json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_prediction_lab_summary(payload))

    return 0


def _run_cfg_command(args: argparse.Namespace) -> int:
    profile = presets_mod.resolve_profile(args.profile if getattr(args, "profile", None) else None)
    paths = profile.get("paths", {})
    pred = profile.get("prediction", {})

    if getattr(args, "json", False):
        import json as _json

        print(_json.dumps(profile, ensure_ascii=False, indent=2))
        return 0

    width = profile.get("ui", {}).get("width", 120)
    print("PYMERCATOR CFG")
    print(ui.line(width))
    print(ui.kv("PROFILE", profile.get("profile")))
    print(ui.kv("PRICES DIR", paths.get("prices_dir")))
    print(ui.kv("UNIVERSE", paths.get("universe_output")))
    print(ui.kv("FEATURE MATRIX", paths.get("feature_matrix")))
    print(ui.kv("PRED DATASET", paths.get("prediction_dataset")))
    print(ui.kv("EVALUATION", paths.get("prediction_evaluation")))
    print(ui.kv("ENGINES", ",".join(pred.get("engines", []))))
    print(ui.kv("N JOBS", pred.get("n_jobs")))
    print(ui.kv("HORIZON", pred.get("horizon")))
    print(ui.kv("MIN HISTORY", pred.get("min_history")))
    print(ui.kv("MIN TRAIN ROWS", pred.get("min_train_rows")))
    print(ui.kv("AUTOTUNE", "ON" if pred.get("autotune") else "OFF"))

    return 0


def _run_short_board_command(args: argparse.Namespace) -> int:
    profile = presets_mod.resolve_profile(args.profile if getattr(args, "profile", None) else None)
    paths = profile.get("paths", {})

    run_dir = paths.get("scenario_runs")
    manifest_path = None

    try:
        from pathlib import Path

        base = Path(run_dir)
        if base.exists() and base.is_dir():
            candidates = [p for p in base.iterdir() if p.is_dir()]
            candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            if candidates:
                manifest = candidates[0] / "00_manifest.json"
                if manifest.exists():
                    manifest_path = manifest

        print("PYMERCATOR BOARD")
        print(ui.line(profile.get("ui", {}).get("width", 120)))
        print(ui.kv("PACK", str(manifest_path or "(not found)")))
        print(ui.kv("FEATURE MATRIX", paths.get("feature_matrix")))
        print(ui.kv("PREDICTION", paths.get("prediction_evaluation")))

    except Exception:
        print("Unable to render board")

    return 0


def _run_short_open_command(args: argparse.Namespace) -> int:
    profile = presets_mod.resolve_profile(args.profile if getattr(args, "profile", None) else None)
    paths = profile.get("paths", {})
    artifact = getattr(args, "artifact", "eval")

    mapping = {
        "manifest": None,
        "eval": paths.get("prediction_evaluation"),
        "matrix": paths.get("feature_matrix"),
        "dataset": paths.get("prediction_dataset"),
        "summary": paths.get("prediction_evaluation"),
    }

    path = mapping.get(artifact, mapping.get("eval"))

    from pathlib import Path

    if not path:
        print("No artifact path configured")
        return 1

    p = Path(path)
    print(f"PATH: {p}")

    if not p.exists():
        print("(missing)")
        return 1

    if getattr(args, "raw", False):
        print(p.read_text(encoding="utf-8"))
        return 0

    # print short preview
    text = p.read_text(encoding="utf-8")
    lines = text.splitlines()
    for ln in lines[:20]:
        print(ln)

    return 0


def _run_short_diag_command(args: argparse.Namespace) -> int:
    profile = presets_mod.resolve_profile(args.profile if getattr(args, "profile", None) else None)
    paths = profile.get("paths", {})
    from pymercator.legacy_prediction_engines import (
        CATBOOST_AVAILABLE,
        SKLEARN_AVAILABLE,
        XGBOOST_AVAILABLE,
    )
    from pymercator.prediction_config import effective_prediction_config

    prediction_config = effective_prediction_config(path="config/prediction.json")
    observer = prediction_config.get("observer", {})
    training = prediction_config.get("training", {})
    weights = observer.get("weights", {})
    horizon_labels = [
        f"D{int(item)}"
        for item in prediction_config.get("horizons", [])
    ]
    backend = "sklearn" if SKLEARN_AVAILABLE else "unavailable"
    stack_status = "OK" if SKLEARN_AVAILABLE else "DEGRADED"
    weights_text = " ".join(
        f"{key}={float(weights[key]):.2f}"
        for key in horizon_labels
        if key in weights
    )

    print("PYMERCATOR DIAG")
    print(muted_line())
    print(format_kv("prices_dir", paths.get("prices_dir"), label_width=18))
    print(format_kv("feature_matrix", paths.get("feature_matrix"), label_width=18))
    print(format_kv("prediction_eval", paths.get("prediction_evaluation"), label_width=18))
    print("")
    print(
        format_kv_section(
            "PREDICTION STACK",
            [
                ("status", stack_status, stack_status),
                ("config", "config/prediction.json"),
                ("backend", backend),
                ("engine", prediction_config.get("default_engine", "-")),
                ("horizons", ",".join(horizon_labels)),
                ("weights", weights_text),
                ("base_models", ",".join(prediction_config.get("base_engines", []))),
                ("combiner", prediction_config.get("meta_model", "-")),
                ("per_horizon", prediction_config.get("per_horizon_engine", "-")),
                ("observer", observer.get("mode", "-")),
                ("baseline_used", "false", "FALSE"),
            ],
            label_width=18,
        )
    )

    if not getattr(args, "verbose", False):
        return 0

    print("")
    print(
        format_kv_section(
            "TECHNICAL CONFIG",
            [
                ("mode", "operational"),
                ("config", "config/prediction.json"),
                ("per_horizon_engine", prediction_config.get("per_horizon_engine", "-")),
                (
                    "horizons",
                    ",".join(
                        str(int(item))
                        for item in prediction_config.get("horizons", [])
                    ),
                ),
                ("base_engines", ",".join(prediction_config.get("base_engines", []))),
                ("meta_model", prediction_config.get("meta_model", "-")),
                ("observer", observer.get("mode", "-")),
                ("weights", weights_text),
                ("min_assets", prediction_config.get("min_assets", "-")),
                ("autotune", str(bool(training.get("autotune", False))).lower()),
                ("n_jobs", training.get("n_jobs", "-")),
            ],
            label_width=22,
        )
    )
    print("")
    print(
        format_kv_section(
            "LIBRARIES",
            [
                ("sklearn available", bool(SKLEARN_AVAILABLE), bool(SKLEARN_AVAILABLE)),
                ("xgboost available", bool(XGBOOST_AVAILABLE), bool(XGBOOST_AVAILABLE)),
                ("catboost available", bool(CATBOOST_AVAILABLE), bool(CATBOOST_AVAILABLE)),
            ],
            label_width=22,
        )
    )
    print("")
    sklearn_engine_status = "available" if SKLEARN_AVAILABLE else "unavailable"
    print(
        format_kv_section(
            "TECHNICAL PREDICTION ENGINES",
            [
                ("rolling_majority", "available baseline"),
                ("extratrees", sklearn_engine_status, sklearn_engine_status),
                ("randomforest", sklearn_engine_status, sklearn_engine_status),
                ("gradientboosting", sklearn_engine_status, sklearn_engine_status),
                ("ridge", sklearn_engine_status, sklearn_engine_status),
                ("ridge_ensemble", f"{sklearn_engine_status} per-horizon"),
                ("multi_horizon_ridge", f"{sklearn_engine_status} default"),
            ],
            label_width=22,
        )
    )

    return 0


def _run_basket_command(args: argparse.Namespace) -> int:
    from pymercator.cli_basket import run_basket_cli

    return run_basket_cli(args)


def _run_daily_auto_command(args: argparse.Namespace) -> int:
    from pymercator.cli_daily_auto import run_daily_auto_command

    return run_daily_auto_command(args)


def _run_real_pack_command(args: argparse.Namespace) -> int:
    from pymercator.cli_real_pack import run_real_pack_command

    args.context_values = resolve_market_context_args(args)
    return run_real_pack_command(args)


def _run_daily_command(args: argparse.Namespace) -> int:
    resolved_output, json_output, resolved_run_dir = _resolve_output_paths(
        output=args.output,
        json_output=args.json_output,
        run_dir=args.run_dir,
    )

    context_values = resolve_market_context_args(args)

    from pymercator.cli_daily import run_daily_command

    return run_daily_command(
        args=args,
        resolved_output=resolved_output,
        json_output=json_output,
        resolved_run_dir=resolved_run_dir,
        context_values=context_values,
    )


def _run_scenario_pack_command(args: argparse.Namespace) -> int:
    from pymercator.cli_scenario_pack import run_scenario_pack_command

    args.context_values = resolve_market_context_args(args)
    return run_scenario_pack_command(args)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _pack_top_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    scenarios = summary.get("scenarios", [])

    if not scenarios:
        return {}

    active = next(
        (
            scenario
            for scenario in scenarios
            if scenario.get("key") == "03_active_agr"
        ),
        None,
    )

    selected = active or scenarios[0]
    top = selected.get("top", {})

    return {
        "scenario": selected.get("key", "-"),
        "ticker": top.get("ticker", "-"),
        "permission": top.get("permission", "-"),
        "label": top.get("decision_label", "-"),
    }


def build_parser() -> argparse.ArgumentParser:
        engines_help = _prediction_engines_help()
        train_horizons_help = (
            f"Prediction horizons in trading days. Default: {DEFAULT_TRAIN_HORIZONS}"
        )
        train_engines_help = (
            "Base engines for multi_horizon_ridge. Valid: extratrees, "
            "randomforest, gradientboosting. Baseline: rolling_majority"
        )
        train_n_jobs_help = f"Parallel workers. Default: {DEFAULT_TRAIN_N_JOBS}"
        train_min_history_help = (
            f"Minimum price history. Default: {DEFAULT_TRAIN_MIN_HISTORY}"
        )
        train_min_train_rows_help = (
            f"Minimum training rows. Default: {DEFAULT_TRAIN_MIN_TRAIN_ROWS}"
        )
        train_autotune_iter_help = f"Autotune iterations. Default: {DEFAULT_TRAIN_AUTOTUNE_ITER}"
        train_autotune_cv_help = f"Autotune CV folds. Default: {DEFAULT_TRAIN_AUTOTUNE_CV}"
        train_calibration_method_help = (
            "Probability calibration method. Valid: sigmoid, isotonic. "
            f"Default: {DEFAULT_TRAIN_CALIBRATION_METHOD}"
        )
        train_calibration_cv_help = (
            f"Probability calibration CV folds. Default: {DEFAULT_TRAIN_CALIBRATION_CV}"
        )
        train_threshold_metric_help = (
            "Threshold tuning metric. Valid: balanced_accuracy, accuracy, f1, youden. "
            f"Default: {DEFAULT_TRAIN_THRESHOLD_METRIC}"
        )
        horizon_help = (
            f"Prediction horizon in trading days. Default: {DEFAULT_PREDICTION_HORIZON}"
        )
        n_jobs_help = f"Parallel workers. Default: {DEFAULT_PREDICTION_N_JOBS}"
        min_history_help = (
            f"Minimum price history. Default: {DEFAULT_PREDICTION_MIN_HISTORY}"
        )
        min_train_rows_help = (
            f"Minimum training rows. Default: {DEFAULT_PREDICTION_MIN_TRAIN_ROWS}"
        )
        parser = argparse.ArgumentParser(
            prog="pymercator",
            description="pyMercator command line interface",
        )
        parser.add_argument(
            "--color",
            choices=["auto", "always", "never"],
            default="auto",
            help="Terminal colors: auto, always, never. Default: auto",
        )
        parser.add_argument(
            "--no-color",
            action="store_true",
            help="Disable terminal colors.",
        )
        parser.add_argument(
            "--palette",
            default="",
            help="Terminal palette from config/ui.json. Default: configured default.",
        )
        parser.add_argument(
            "--ui-config",
            default="config/ui.json",
            help="Terminal UI config file. Default: config/ui.json",
        )
        subparsers = parser.add_subparsers(dest="command")

        # Official routine commands
        update_parser = subparsers.add_parser("update", help="Update operational data")
        update_parser.set_defaults(command="update")
        update_parser.add_argument("--list", default="IBOV")
        update_parser.add_argument("--start", default="2000-01-01")
        update_parser.add_argument("--end", default="")
        update_parser.add_argument("--no-cache", action="store_true")
        update_parser.add_argument("--tickers-file", default="")
        update_parser.add_argument("--prices-dir", default="data/prices")
        update_parser.add_argument("--indices-catalog", default="config/indices_catalog.json")
        update_parser.add_argument("--indices-dir", default="data/indices")
        update_parser.add_argument(
            "--context-output",
            default="storage/context/latest_market_context.json",
        )
        update_parser.add_argument("--universe-output", default="data/universes/ibov_live.csv")
        update_parser.add_argument("--features-catalog", default="config/features_catalog.json")
        update_parser.add_argument(
            "--matrix-output",
            default="storage/features/latest_feature_matrix.csv",
        )
        update_parser.add_argument("--json", action="store_true")

        train_parser = subparsers.add_parser(
            "train",
            help="Train multi-horizon prediction ensemble. Profile-independent.",
            description="Train multi-horizon prediction ensemble. Profile-independent.",
        )
        train_parser.set_defaults(command="train", detail_engines=False)
        train_parser.add_argument("--profile", default="", help=argparse.SUPPRESS)
        train_parser.add_argument(
            "--details",
            action="store_true",
            help="Print operational training detail report.",
        )
        train_parser.add_argument(
            "--prob-dist",
            action="store_true",
            help="Include probability distribution buckets in --details.",
        )
        train_parser.add_argument(
            "--full",
            action="store_true",
            help="Include all detail report sections.",
        )
        train_parser.add_argument(
            "--output",
            default="",
            help="Write detailed training report TXT. Used with --details.",
        )
        train_parser.add_argument(
            "--config",
            default="config/prediction.json",
            help="Prediction config file. Default: config/prediction.json",
        )
        train_parser.add_argument(
            "--horizons",
            default="",
            help=train_horizons_help,
        )
        train_parser.add_argument(
            "--horizon",
            type=int,
            default=None,
            help=argparse.SUPPRESS,
        )
        train_parser.add_argument("--matrix", default="storage/features/latest_feature_matrix.csv")
        train_parser.add_argument("--universe", default="data/universes/ibov_live.csv")
        train_parser.add_argument("--prices-dir", default="data/prices")
        train_parser.add_argument(
            "--dataset-output",
            default="storage/prediction/latest_dataset.csv",
        )
        train_parser.add_argument(
            "--evaluation-output",
            default="storage/prediction/latest_evaluation.json",
        )
        train_parser.add_argument(
            "--min-history",
            type=int,
            default=None,
            help=train_min_history_help,
        )
        train_parser.add_argument(
            "--min-train-rows",
            type=int,
            default=None,
            help=train_min_train_rows_help,
        )
        train_parser.add_argument(
            "--engines",
            action=_TrainEnginesAction,
            default="",
            metavar="ENGINES",
            help=(
                f"{train_engines_help} With --details, a bare --engines includes "
                "complete base engine metrics."
            ),
        )
        train_parser.add_argument("--meta", default="", help="Meta model. Default: ridge")
        train_parser.add_argument(
            "--observer",
            default="",
            help="Horizon observer mode. Default: weighted",
        )
        train_parser.add_argument(
            "--weights",
            default="",
            help="Horizon weights, e.g. D5=0.25,D20=0.35,D60=0.4",
        )
        train_parser.add_argument("--independent-horizons", action="store_true")
        train_parser.add_argument("--combined-horizons", action="store_true")
        train_parser.add_argument(
            "--n-jobs",
            type=int,
            default=None,
            help=train_n_jobs_help,
        )
        train_parser.add_argument("--autotune", action="store_true", default=None)
        train_parser.add_argument(
            "--autotune-iter",
            type=int,
            default=None,
            help=train_autotune_iter_help,
        )
        train_parser.add_argument(
            "--autotune-cv",
            type=int,
            default=None,
            help=train_autotune_cv_help,
        )
        train_parser.add_argument(
            "--calibration-method",
            choices=["sigmoid", "isotonic"],
            default="",
            help=train_calibration_method_help,
        )
        train_parser.add_argument(
            "--calibration-cv",
            type=int,
            default=None,
            help=train_calibration_cv_help,
        )
        train_parser.add_argument(
            "--threshold-metric",
            choices=["balanced_accuracy", "accuracy", "f1", "youden"],
            default="",
            help=train_threshold_metric_help,
        )
        train_parser.add_argument(
            "--disable-calibration",
            action="store_true",
            help="Disable probability calibration for base engines.",
        )
        train_parser.add_argument(
            "--experimental",
            action="store_true",
            help="Allow non-operational train settings and mark the evaluation experimental.",
        )
        train_parser.add_argument(
            "--allow-small-universe",
            action="store_true",
            help="Allow assets below operational min_assets; requires --experimental.",
        )
        train_parser.add_argument("--json", action="store_true")

        run_parser = subparsers.add_parser(
            "run",
            help="Run daily decision using an operational profile.",
            description="Run daily decision using an operational profile.",
        )
        run_parser.set_defaults(command="run")
        run_parser.add_argument("--profile", default="CON")
        run_parser.add_argument("--list", default="IBOV")
        run_parser.add_argument("--policy", default="config/policy.json")
        run_parser.add_argument("--universe", default="data/universes/ibov_live.csv")
        run_parser.add_argument("--context", default="storage/context/latest_market_context.json")
        run_parser.add_argument("--matrix", default="storage/features/latest_feature_matrix.csv")
        run_parser.add_argument("--evaluation", default="storage/prediction/latest_evaluation.json")
        run_parser.add_argument("--observation-config", default="config/observation.json")
        run_parser.add_argument("--prices-dir", default="data/prices")
        run_parser.add_argument("--limit", type=int, default=20)
        run_parser.add_argument("--run-dir", default="storage/runs/latest")
        run_parser.add_argument(
            "--report-output",
            default="storage/reports/latest_daily_report.txt",
        )
        run_parser.add_argument(
            "--json-output",
            default="storage/reports/latest_daily_report.json",
        )
        run_parser.add_argument("--basket", action="store_true")
        run_parser.add_argument("--slots", type=int, default=5)
        run_parser.add_argument("--min-sectors", type=int, default=3)
        run_parser.add_argument("--min-weight", type=float, default=0.10)
        run_parser.add_argument("--capital", type=float, default=100000.0)
        run_parser.add_argument("--risk-per-trade", type=float, default=0.005)
        run_parser.add_argument("--targets", type=int, default=2)
        run_parser.add_argument("--stop", default="progressive", choices=["progressive"])
        run_parser.add_argument(
            "--basket-output",
            default="storage/baskets/latest_daily_basket.csv",
        )
        run_parser.add_argument("--allow-experimental-model", action="store_true")
        run_parser.add_argument("--json", action="store_true")

        observe_parser = subparsers.add_parser(
            "observe",
            help="Rank assets for observation without generating trade signals.",
            description="Rank assets for observation without generating trade signals.",
        )
        observe_parser.set_defaults(command="observe")
        observe_parser.add_argument("--list", default="IBOV")
        observe_parser.add_argument("--universe", default="data/universes/ibov_live.csv")
        observe_parser.add_argument("--config", default="config/observation.json")
        observe_parser.add_argument("--limit", type=int, default=20)
        observe_parser.add_argument("--cluster", action="store_true")
        observe_parser.add_argument("--json", action="store_true")

        lab_short = subparsers.add_parser("lab", help="Run prediction lab (shortcut)")
        lab_short.set_defaults(command="lab")
        lab_short.add_argument("--fast", action="store_true")
        lab_short.add_argument("--engines", default="", help=engines_help)
        lab_short.add_argument("--autotune", action="store_true")
        lab_short.add_argument(
            "--jobs",
            type=int,
            default=0,
            help="Number of jobs (alias for n-jobs)",
        )
        lab_short.add_argument("--horizon", type=int, default=0)
        lab_short.add_argument("--profile", default="")
        lab_short.add_argument("--json", action="store_true")

        cfg_short = subparsers.add_parser("cfg", help="Show effective configuration")
        cfg_short.set_defaults(command="cfg")
        cfg_short.add_argument("--profile", default="")
        cfg_short.add_argument("--json", action="store_true")

        board_short = subparsers.add_parser("board", help="Show last pack dashboard")
        board_short.set_defaults(command="board")
        board_short.add_argument("--profile", default="")
        board_short.add_argument("--json", action="store_true")

        open_short = subparsers.add_parser(
            "open",
            help="Open recent artifact (manifest|eval|matrix|dataset)",
        )
        open_short.set_defaults(command="open")
        open_short.add_argument("artifact", nargs="?", default="eval")
        open_short.add_argument("--raw", action="store_true")
        open_short.add_argument("--profile", default="")

        diag_short = subparsers.add_parser("diag", help="Quick diagnostics")
        diag_short.set_defaults(command="diag")
        diag_short.add_argument("--profile", default="")
        diag_short.add_argument("--verbose", action="store_true")

        basket_parser = subparsers.add_parser("basket", help="Basket utilities")
        basket_parser.set_defaults(command="basket")
        basket_parser.add_argument("--profile", default="")
        basket_parser.add_argument("--json", action="store_true")
        basket_subparsers = basket_parser.add_subparsers(dest="basket_command")

        basket_daily_parser = basket_subparsers.add_parser("daily", help="Create daily basket")
        basket_daily_parser.set_defaults(basket_command="daily")
        basket_daily_parser.add_argument("--slots", type=int, default=5)
        basket_daily_parser.add_argument("--min-sectors", type=int, default=3)
        basket_daily_parser.add_argument("--min-weight", type=float, default=0.10)
        basket_daily_parser.add_argument("--capital", type=float, default=100000.0)
        basket_daily_parser.add_argument("--risk-per-trade", type=float, default=0.005)
        basket_daily_parser.add_argument("--targets", type=int, default=2)
        basket_daily_parser.add_argument(
            "--stop",
            default="progressive",
            choices=["progressive"],
        )
        default_paths = presets_mod.resolve_profile(None).get("paths", {})
        basket_daily_parser.add_argument(
            "--prices-dir",
            default=default_paths.get("prices_dir", "data/prices"),
        )
        basket_daily_parser.add_argument(
            "--universe",
            default=default_paths.get(
                "universe_output",
                "data/universes/ibov_live.csv",
            ),
        )
        basket_daily_parser.add_argument(
            "--matrix",
            default=default_paths.get(
                "feature_matrix",
                "storage/features/latest_feature_matrix.csv",
            ),
        )
        basket_daily_parser.add_argument(
            "--evaluation",
            default=default_paths.get(
                "prediction_evaluation",
                "storage/prediction/latest_evaluation.json",
            ),
        )
        basket_daily_parser.add_argument(
            "--output",
            default="storage/baskets/latest_daily_basket.csv",
        )
        basket_daily_parser.add_argument("--daily-report", default="")

        basket_show_parser = basket_subparsers.add_parser("show", help="Show latest basket")
        basket_show_parser.set_defaults(basket_command="show")
        basket_show_parser.add_argument(
            "--output",
            default="storage/baskets/latest_daily_basket.csv",
        )
        basket_show_parser.add_argument("--details", action="store_true")

        daily_parser = subparsers.add_parser("daily", help="Run daily report")
        daily_parser.set_defaults(command="daily")
        daily_parser.add_argument("--universe", required=True)
        daily_parser.add_argument("--universe-name", default="IBOV")
        daily_parser.add_argument("--profile", default="")
        daily_parser.add_argument("--headline-risk", default="OFF")
        daily_parser.add_argument("--policy", default="config/policy.json")
        daily_parser.add_argument("--limit", type=int, default=0)
        daily_parser.add_argument("--output", default="")
        daily_parser.add_argument("--json-output", default="")
        daily_parser.add_argument("--run-dir", default="")
        daily_parser.add_argument("--context", default="")
        daily_parser.add_argument("--context-preset", default="")
        daily_parser.add_argument("--headline-tags", default="")
        daily_parser.add_argument("--market-trend", default="CHOPPY")
        daily_parser.add_argument("--market-volatility", default="NORMAL")

        real_pack_parser = subparsers.add_parser("daily-real", help="Run real pack")
        real_pack_parser.set_defaults(command="daily-real")
        real_pack_parser.add_argument("--execution-policy", default="config/execution_policy.json")
        real_pack_parser.add_argument("--tickers-file", required=True)
        real_pack_parser.add_argument("--features-file", default="config/features_catalog.json")
        real_pack_parser.add_argument("--start", default="")
        real_pack_parser.add_argument("--end", default="")
        real_pack_parser.add_argument("--prices-dir", required=True)
        real_pack_parser.add_argument("--universe-output", required=True)
        real_pack_parser.add_argument("--run-dir", default="storage/scenario_runs")
        real_pack_parser.add_argument("--universe-name", default="IBOV")
        real_pack_parser.add_argument("--policy", default="config/policy.json")
        real_pack_parser.add_argument("--limit", type=int, default=0)
        real_pack_parser.add_argument("--skip-fetch", action="store_true")
        real_pack_parser.add_argument("--json", action="store_true")
        real_pack_parser.add_argument("--context", default="")
        real_pack_parser.add_argument("--context-preset", default="")
        real_pack_parser.add_argument("--headline-tags", default="")
        real_pack_parser.add_argument("--market-trend", default="CHOPPY")
        real_pack_parser.add_argument("--market-volatility", default="NORMAL")

        real_pack_alias_parser = subparsers.add_parser("real-pack", help="Run real pack")
        real_pack_alias_parser.set_defaults(command="real-pack")
        real_pack_alias_parser.add_argument(
            "--execution-policy",
            default="config/execution_policy.json",
        )
        real_pack_alias_parser.add_argument("--tickers-file", required=True)
        real_pack_alias_parser.add_argument(
            "--features-file",
            default="config/features_catalog.json",
        )
        real_pack_alias_parser.add_argument("--start", default="")
        real_pack_alias_parser.add_argument("--end", default="")
        real_pack_alias_parser.add_argument("--prices-dir", required=True)
        real_pack_alias_parser.add_argument("--universe-output", required=True)
        real_pack_alias_parser.add_argument("--run-dir", default="storage/scenario_runs")
        real_pack_alias_parser.add_argument("--universe-name", default="IBOV")
        real_pack_alias_parser.add_argument("--policy", default="config/policy.json")
        real_pack_alias_parser.add_argument("--limit", type=int, default=0)
        real_pack_alias_parser.add_argument("--skip-fetch", action="store_true")
        real_pack_alias_parser.add_argument("--json", action="store_true")
        real_pack_alias_parser.add_argument("--context", default="")
        real_pack_alias_parser.add_argument("--context-preset", default="")
        real_pack_alias_parser.add_argument("--headline-tags", default="")
        real_pack_alias_parser.add_argument("--market-trend", default="CHOPPY")
        real_pack_alias_parser.add_argument("--market-volatility", default="NORMAL")

        scenario_pack_parser = subparsers.add_parser("scenario-pack", help="Create a scenario pack")
        scenario_pack_parser.set_defaults(command="scenario-pack")
        scenario_pack_parser.add_argument("--universe", required=True)
        scenario_pack_parser.add_argument("--universe-name", default="IBOV")
        scenario_pack_parser.add_argument("--policy", default="config/policy.json")
        scenario_pack_parser.add_argument("--run-dir", default="storage/scenario_runs")
        scenario_pack_parser.add_argument("--limit", type=int, default=0)
        scenario_pack_parser.add_argument("--context", default="")
        scenario_pack_parser.add_argument("--context-preset", default="")
        scenario_pack_parser.add_argument("--headline-tags", default="")
        scenario_pack_parser.add_argument("--market-trend", default="CHOPPY")
        scenario_pack_parser.add_argument("--market-volatility", default="NORMAL")

        scenario_parser = subparsers.add_parser("scenario", help="Scenario utilities")
        scenario_parser.set_defaults(command="scenario")
        scenario_subparsers = scenario_parser.add_subparsers(dest="scenario_command")
        scenario_run_parser = scenario_subparsers.add_parser(
            "run",
            help="Run a synthetic operational scenario",
        )
        scenario_run_parser.set_defaults(scenario_command="run")
        scenario_run_parser.add_argument("--preset", default="positive_risk_on")
        scenario_run_parser.add_argument("--profile", default="AGR")
        scenario_run_parser.add_argument("--policy", default="config/policy.json")
        scenario_run_parser.add_argument("--output-root", default="storage/scenarios")
        scenario_run_parser.add_argument(
            "--report-output",
            default="storage/reports/latest_daily_report.txt",
        )
        scenario_run_parser.add_argument(
            "--json-output",
            default="storage/reports/latest_daily_report.json",
        )
        scenario_run_parser.add_argument("--run-dir", default="storage/runs/latest")
        scenario_run_parser.add_argument("--limit", type=int, default=5)
        scenario_run_parser.add_argument("--basket", action="store_true")
        scenario_run_parser.add_argument(
            "--basket-output",
            default="storage/baskets/latest_daily_basket.csv",
        )
        scenario_run_parser.add_argument("--slots", type=int, default=5)
        scenario_run_parser.add_argument("--min-sectors", type=int, default=3)
        scenario_run_parser.add_argument("--min-weight", type=float, default=0.10)
        scenario_run_parser.add_argument("--capital", type=float, default=100000.0)
        scenario_run_parser.add_argument("--risk-per-trade", type=float, default=0.005)
        scenario_run_parser.add_argument("--json", action="store_true")

        daily_auto_parser = subparsers.add_parser("daily-auto", help="Run daily auto workflow")
        daily_auto_parser.set_defaults(command="daily-auto")
        daily_auto_parser.add_argument("--execution-policy", default="config/execution_policy.json")
        daily_auto_parser.add_argument("--indices-catalog", default="config/indices_catalog.json")
        daily_auto_parser.add_argument("--indices-start", default="2000-01-01")
        daily_auto_parser.add_argument("--indices-dir", default="data/indices")
        daily_auto_parser.add_argument(
            "--context-output",
            default="config/market_context_auto.json",
        )
        daily_auto_parser.add_argument("--features-file", default="config/features_catalog.json")
        daily_auto_parser.add_argument(
            "--feature-matrix-output",
            default="storage/features/latest_feature_matrix.csv",
        )
        daily_auto_parser.add_argument(
            "--prediction-dataset-output",
            default="storage/prediction/latest_prediction_dataset.csv",
        )
        daily_auto_parser.add_argument(
            "--prediction-evaluation-output",
            default="storage/prediction/latest_evaluation.json",
        )
        daily_auto_parser.add_argument("--prediction-horizon", type=int, default=5)
        daily_auto_parser.add_argument("--prediction-min-history", type=int, default=20)
        daily_auto_parser.add_argument("--prediction-min-train-rows", type=int, default=100)
        daily_auto_parser.add_argument("--prediction-engines", default="", help=engines_help)
        daily_auto_parser.add_argument("--prediction-n-jobs", type=int, default=4)
        daily_auto_parser.add_argument("--prediction-autotune", action="store_true")
        daily_auto_parser.add_argument("--prediction-autotune-iter", type=int, default=15)
        daily_auto_parser.add_argument("--prediction-autotune-cv", type=int, default=3)
        daily_auto_parser.add_argument("--tickers-file", default="data/universes/ibov_tickers.csv")
        daily_auto_parser.add_argument("--sentiment-dir", default="data/sentiment")
        daily_auto_parser.add_argument("--prices-start", default="2000-01-01")
        daily_auto_parser.add_argument("--prices-dir", default="data/prices")
        daily_auto_parser.add_argument("--universe-output", default="data/universes/ibov_live.csv")
        daily_auto_parser.add_argument("--run-dir", default="storage/scenario_runs")
        daily_auto_parser.add_argument("--universe-name", default="IBOV")
        daily_auto_parser.add_argument("--policy", default="config/policy.json")
        daily_auto_parser.add_argument("--skip-asset-fetch", action="store_true")
        daily_auto_parser.add_argument("--skip-indices-fetch", action="store_true")
        daily_auto_parser.add_argument("--json", action="store_true")

        context_parser = subparsers.add_parser("context", help="Manage market context")
        context_parser.set_defaults(command="context")
        context_parser.add_argument("--json", action="store_true")
        context_parser.add_argument("--context", default="")
        context_parser.add_argument("--context-preset", default="")
        context_parser.add_argument("--headline-tags", default="")
        context_parser.add_argument("--market-trend", default="CHOPPY")
        context_parser.add_argument("--market-volatility", default="NORMAL")
        context_subparsers = context_parser.add_subparsers(dest="context_command")
        _auto_ctx = context_subparsers.add_parser(
            "auto",
            help="Auto generate market context",
        )
        _auto_ctx.set_defaults(context_command="auto")
        _auto_ctx.add_argument("--indices-dir", required=True)
        _auto_ctx.add_argument("--output", required=True)

        _tmpl_ctx = context_subparsers.add_parser(
            "template",
            help="Write market context template",
        )
        _tmpl_ctx.set_defaults(context_command="template")
        _tmpl_ctx.add_argument("--output", required=True)
        context_subparsers.add_parser(
            "presets",
            help="List available market context presets",
        ).set_defaults(context_command="presets")
        check_context_parser = context_subparsers.add_parser(
            "check",
            help="Validate a market context file",
        )
        check_context_parser.set_defaults(context_command="check")
        check_context_parser.add_argument("--file", required=True)


        execution_parser = subparsers.add_parser(
            "execution",
            help="Execution policy utilities",
        )
        execution_parser.set_defaults(command="execution")
        execution_parser.add_argument("--json", action="store_true")
        execution_subparsers = execution_parser.add_subparsers(dest="execution_command")
        execution_template_parser = execution_subparsers.add_parser(
            "template",
            help="Write execution policy template",
        )
        execution_template_parser.set_defaults(execution_command="template")
        execution_template_parser.add_argument("--output", required=True)
        execution_check_parser = execution_subparsers.add_parser(
            "check",
            help="Validate execution policy",
        )
        execution_check_parser.set_defaults(execution_command="check")
        execution_check_parser.add_argument("--file", required=True)

        indices_parser = subparsers.add_parser("indices", help="Indices utilities")
        indices_parser.set_defaults(command="indices")
        indices_parser.add_argument("--json", action="store_true")
        indices_subparsers = indices_parser.add_subparsers(dest="indices_command")
        indices_fetch_parser = indices_subparsers.add_parser("fetch", help="Fetch indices prices")
        indices_fetch_parser.set_defaults(indices_command="fetch")
        indices_fetch_parser.add_argument("--catalog", required=True)
        indices_fetch_parser.add_argument("--start", required=True)
        indices_fetch_parser.add_argument("--end", default="")
        indices_fetch_parser.add_argument("--no-cache", action="store_true")
        indices_fetch_parser.add_argument("--output", required=True)
        indices_prices_check_parser = indices_subparsers.add_parser(
            "prices-check",
            help="Check indices prices",
        )
        indices_prices_check_parser.set_defaults(indices_command="prices-check")
        indices_prices_check_parser.add_argument("--prices-dir", required=True)
        indices_catalog_parser = indices_subparsers.add_parser(
            "catalog",
            help="Validate indices catalog",
        )
        indices_catalog_parser.set_defaults(indices_command="catalog")
        indices_catalog_parser.add_argument("--file", required=True)
        indices_check_parser = indices_subparsers.add_parser("check", help="Check indices catalog")
        indices_check_parser.set_defaults(indices_command="check")
        indices_check_parser.add_argument("--file", required=True)

        sentiment_parser = subparsers.add_parser("sentiment", help="Sentiment utilities")
        sentiment_parser.set_defaults(command="sentiment")
        sentiment_parser.add_argument("--json", action="store_true")
        sentiment_subparsers = sentiment_parser.add_subparsers(dest="sentiment_command")
        sentiment_check_parser = sentiment_subparsers.add_parser(
            "check",
            help="Check sentiment directory",
        )
        sentiment_check_parser.set_defaults(sentiment_command="check")
        sentiment_check_parser.add_argument("--sentiment-dir", required=True)

        predict_parser = subparsers.add_parser("predict", help="Prediction utilities")
        predict_parser.set_defaults(command="predict")
        predict_parser.add_argument("--json", action="store_true")
        predict_subparsers = predict_parser.add_subparsers(dest="predict_command")
        predict_dataset_parser = predict_subparsers.add_parser(
            "dataset",
            help="Write prediction dataset",
        )
        predict_dataset_parser.set_defaults(predict_command="dataset")
        predict_dataset_parser.add_argument("--matrix", required=True)
        predict_dataset_parser.add_argument("--prices-dir", required=True)
        predict_dataset_parser.add_argument("--output", required=True)
        predict_dataset_parser.add_argument("--horizon", type=int, default=5)
        predict_dataset_parser.add_argument("--min-history", type=int, default=20)
        predict_evaluate_parser = predict_subparsers.add_parser(
            "evaluate",
            help="Write evaluation report",
        )
        predict_evaluate_parser.set_defaults(predict_command="evaluate")
        predict_evaluate_parser.add_argument("--dataset", required=True)
        predict_evaluate_parser.add_argument("--output", required=True)
        predict_evaluate_parser.add_argument("--horizon", type=int, default=5)
        predict_evaluate_parser.add_argument("--min-train-rows", type=int, default=100)
        predict_evaluate_parser.add_argument("--engines", default="", help=engines_help)
        predict_evaluate_parser.add_argument("--n-jobs", type=int, default=1)
        predict_evaluate_parser.add_argument("--autotune", action="store_true")
        predict_evaluate_parser.add_argument("--autotune-iter", type=int, default=0)
        predict_evaluate_parser.add_argument("--autotune-cv", type=int, default=0)
        predict_lab_parser = predict_subparsers.add_parser("lab", help="Run prediction lab")
        predict_lab_parser.set_defaults(predict_command="lab")
        predict_lab_parser.add_argument("--matrix", required=True)
        predict_lab_parser.add_argument("--prices-dir", required=True)
        predict_lab_parser.add_argument("--dataset-output", required=True)
        predict_lab_parser.add_argument("--evaluation-output", required=True)
        predict_lab_parser.add_argument(
            "--horizon",
            type=int,
            default=DEFAULT_PREDICTION_HORIZON,
            help=horizon_help,
        )
        predict_lab_parser.add_argument(
            "--min-history",
            type=int,
            default=DEFAULT_PREDICTION_MIN_HISTORY,
            help=min_history_help,
        )
        predict_lab_parser.add_argument(
            "--min-train-rows",
            type=int,
            default=DEFAULT_PREDICTION_MIN_TRAIN_ROWS,
            help=min_train_rows_help,
        )
        predict_lab_parser.add_argument("--engines", default="", help=engines_help)
        predict_lab_parser.add_argument(
            "--n-jobs",
            type=int,
            default=DEFAULT_PREDICTION_N_JOBS,
            help=n_jobs_help,
        )
        predict_lab_parser.add_argument("--autotune", action="store_true")
        predict_lab_parser.add_argument("--autotune-iter", type=int, default=0)
        predict_lab_parser.add_argument("--autotune-cv", type=int, default=0)

        features_parser = subparsers.add_parser("features", help="Features utilities")
        features_parser.set_defaults(command="features")
        features_parser.add_argument("--json", action="store_true")
        features_subparsers = features_parser.add_subparsers(dest="features_command")
        features_check_parser = features_subparsers.add_parser(
            "check",
            help="Validate features catalog",
        )
        features_check_parser.set_defaults(features_command="check")
        features_check_parser.add_argument("--file", required=True)
        features_catalog_parser = features_subparsers.add_parser(
            "catalog",
            help="Render features catalog",
        )
        features_catalog_parser.set_defaults(features_command="catalog")
        features_catalog_parser.add_argument("--file", required=True)
        features_matrix_parser = features_subparsers.add_parser(
            "matrix",
            help="Write feature matrix",
        )
        features_matrix_parser.set_defaults(features_command="matrix")
        features_matrix_parser.add_argument("--universe", required=True)
        features_matrix_parser.add_argument("--prices-dir", required=True)
        features_matrix_parser.add_argument("--context", required=True)
        features_matrix_parser.add_argument("--features", required=True)
        features_matrix_parser.add_argument("--output", required=True)

        confirm_parser = subparsers.add_parser("confirm", help="Register human confirmation")
        confirm_parser.set_defaults(command="confirm")
        confirm_parser.add_argument("--pack", required=True)
        confirm_parser.add_argument("--ticker", required=True)
        confirm_parser.add_argument("--decision", required=True)
        confirm_parser.add_argument("--notes", default="")
        confirm_parser.add_argument("--operator", default="")
        confirm_parser.add_argument("--execution-policy", default="config/execution_policy.json")
        confirm_parser.add_argument("--json", action="store_true")

        legacy_parser = subparsers.add_parser("legacy", help="Legacy data migration tools")
        legacy_parser.set_defaults(command="legacy")
        legacy_parser.add_argument("--json", action="store_true")
        legacy_subparsers = legacy_parser.add_subparsers(dest="legacy_command")
        legacy_classify_parser = legacy_subparsers.add_parser(
            "classify",
            help="Classify legacy inventory",
        )
        legacy_classify_parser.set_defaults(legacy_command="classify")
        legacy_classify_parser.add_argument("--inventory", required=True)
        legacy_classify_parser.add_argument("--output", required=True)
        legacy_migrate_sentiment_parser = legacy_subparsers.add_parser(
            "migrate-sentiment",
            help="Migrate legacy sentiment",
        )
        legacy_migrate_sentiment_parser.set_defaults(legacy_command="migrate-sentiment")
        legacy_migrate_sentiment_parser.add_argument("--legacy-path", required=True)
        legacy_migrate_sentiment_parser.add_argument("--source-dir", default="data/sentiment")
        legacy_migrate_sentiment_parser.add_argument("--output", required=True)
        legacy_migrate_features_parser = legacy_subparsers.add_parser(
            "migrate-features",
            help="Migrate legacy features",
        )
        legacy_migrate_features_parser.set_defaults(legacy_command="migrate-features")
        legacy_migrate_features_parser.add_argument("--legacy-path", required=True)
        legacy_migrate_features_parser.add_argument("--output", required=True)
        legacy_migrate_indices_parser = legacy_subparsers.add_parser(
            "migrate-indices",
            help="Migrate legacy indices",
        )
        legacy_migrate_indices_parser.set_defaults(legacy_command="migrate-indices")
        legacy_migrate_indices_parser.add_argument("--legacy-path", required=True)
        legacy_migrate_indices_parser.add_argument(
            "--catalog-file",
            default="config/indices/catalog.yaml",
        )
        legacy_migrate_indices_parser.add_argument("--output", required=True)
        legacy_migrate_universe_parser = legacy_subparsers.add_parser(
            "migrate-universe",
            help="Migrate legacy universe",
        )
        legacy_migrate_universe_parser.set_defaults(legacy_command="migrate-universe")
        legacy_migrate_universe_parser.add_argument("--legacy-path", required=True)
        legacy_migrate_universe_parser.add_argument(
            "--assets-file",
            default="config/assets/ibov_assets.yaml",
        )
        legacy_migrate_universe_parser.add_argument(
            "--universe-file",
            default="config/universes/ibov.yaml",
        )
        legacy_migrate_universe_parser.add_argument("--output", required=True)
        legacy_scan_parser = legacy_subparsers.add_parser("scan", help="Scan legacy inventory")
        legacy_scan_parser.set_defaults(legacy_command="scan")
        legacy_scan_parser.add_argument("--path", required=True)
        legacy_scan_parser.add_argument("--output", required=True)

        packs_parser = subparsers.add_parser("packs", help="List generated packs")
        packs_parser.set_defaults(command="packs")
        packs_parser.add_argument("--run-dir", required=True)
        packs_parser.add_argument("--limit", type=int, default=10)
        packs_parser.add_argument("--json", action="store_true")

        prices_parser = subparsers.add_parser("prices", help="Manage prices data")
        prices_parser.set_defaults(command="prices")
        prices_parser.add_argument("--json", action="store_true")
        prices_subparsers = prices_parser.add_subparsers(dest="prices_command")
        prices_fetch_parser = prices_subparsers.add_parser("fetch", help="Fetch prices")
        prices_fetch_parser.set_defaults(prices_command="fetch")
        prices_fetch_parser.add_argument("--tickers", default="")
        prices_fetch_parser.add_argument("--start", required=True)
        prices_fetch_parser.add_argument("--end", default="")
        prices_fetch_parser.add_argument("--no-cache", action="store_true")
        prices_fetch_parser.add_argument("--output", required=True)
        prices_fetch_list_parser = prices_subparsers.add_parser(
            "fetch-list",
            help="Fetch prices list",
        )
        prices_fetch_list_parser.set_defaults(prices_command="fetch-list")
        prices_fetch_list_parser.add_argument("--tickers-file", required=True)
        prices_fetch_list_parser.add_argument("--start", required=True)
        prices_fetch_list_parser.add_argument("--end", default="")
        prices_fetch_list_parser.add_argument("--no-cache", action="store_true")
        prices_fetch_list_parser.add_argument("--output", required=True)
        prices_tickers_template_parser = prices_subparsers.add_parser(
            "tickers-template",
            help="Write tickers template",
        )
        prices_tickers_template_parser.set_defaults(prices_command="tickers-template")
        prices_tickers_template_parser.add_argument("--output", required=True)
        prices_tickers_check_parser = prices_subparsers.add_parser(
            "tickers-check",
            help="Check tickers list",
        )
        prices_tickers_check_parser.set_defaults(prices_command="tickers-check")
        prices_tickers_check_parser.add_argument("--file", required=True)
        prices_check_parser = prices_subparsers.add_parser("check", help="Check prices directory")
        prices_check_parser.set_defaults(prices_command="check")
        prices_check_parser.add_argument("--prices-dir", required=True)

        universe_parser = subparsers.add_parser("universe", help="Universe utilities")
        universe_parser.set_defaults(command="universe")
        universe_parser.add_argument("--json", action="store_true")
        universe_subparsers = universe_parser.add_subparsers(dest="universe_command")
        universe_check_parser = universe_subparsers.add_parser("check", help="Check universe file")
        universe_check_parser.set_defaults(universe_command="check")
        universe_check_parser.add_argument("--file", required=True)
        universe_summary_parser = universe_subparsers.add_parser(
            "summary",
            help="Summarize universe file",
        )
        universe_summary_parser.set_defaults(universe_command="summary")
        universe_summary_parser.add_argument("--file", required=True)
        universe_template_parser = universe_subparsers.add_parser(
            "template",
            help="Write universe template",
        )
        universe_template_parser.set_defaults(universe_command="template")
        universe_template_parser.add_argument("--output", required=True)
        universe_build_parser = universe_subparsers.add_parser(
            "build",
            help="Build universe from prices",
        )
        universe_build_parser.set_defaults(universe_command="build")
        universe_build_parser.add_argument("--prices-dir", required=True)
        universe_build_parser.add_argument("--output", required=True)
        universe_build_parser.add_argument("--sentiment-dir", default="")
        universe_build_parser.add_argument("--tickers-file", default="")
        universe_diagnose_parser = universe_subparsers.add_parser(
            "diagnose",
            help="Diagnose universe file",
        )
        universe_diagnose_parser.set_defaults(universe_command="diagnose")
        universe_diagnose_parser.add_argument("--file", required=True)
        universe_diagnose_parser.add_argument("--policy", default="config/policy.json")
        universe_diagnose_parser.add_argument("--details", action="store_true")

        return parser


def main(argv: list[str] | None = None) -> int:
    cleaned_argv, color_mode, palette, ui_config = _extract_ui_args(argv)
    if ui_config:
        set_ui_config_path(ui_config)
    set_color_mode(color_mode)
    set_palette(palette)
    parser = build_parser()
    args = parser.parse_args(cleaned_argv)
    args.color = color_mode
    args.no_color = color_mode == "never"
    args.palette = palette
    args.ui_config = ui_config or "config/ui.json"

    try:
        if args.command == "daily":
            return _run_daily_command(args)

        if args.command == "scenario-pack":
            return _run_scenario_pack_command(args)

        if args.command == "scenario":
            return _run_scenario_command(args)

        if args.command == "packs":
            return _run_packs_command(args)

        if args.command == "daily-real":
            return _run_real_pack_command(args)

        if args.command == "daily-auto":
            return _run_daily_auto_command(args)

        if args.command == "update":
            return _run_update_command(args)

        if args.command == "train":
            return _run_train_command(args)

        if args.command == "run":
            return _run_run_command(args)

        if args.command == "observe":
            return _run_observe_command(args)

        if args.command == "lab":
            return _run_short_lab_command(args)

        if args.command == "cfg":
            return _run_cfg_command(args)

        if args.command == "board":
            return _run_short_board_command(args)

        if args.command == "open":
            return _run_short_open_command(args)

        if args.command == "diag":
            return _run_short_diag_command(args)

        if args.command == "basket":
            return _run_basket_command(args)

        if args.command == "context":
            return _run_context_command(args)

        if args.command == "execution":
            return _run_execution_command(args)

        if args.command == "indices":
            return _run_indices_command(args)

        if args.command == "sentiment":
            return _run_sentiment_command(args)

        if args.command == "predict":
            return _run_predict_command(args)

        if args.command == "features":
            return _run_features_command(args)

        if args.command == "confirm":
            return _run_confirm_command(args)

        if args.command == "legacy":
            return _run_legacy_command(args)

        if args.command == "real-pack":
            return _run_real_pack_command(args)

        if args.command == "prices":
            return _run_prices_command(args)

        if args.command == "packs":
            return _run_packs_command(args)

        if args.command == "daily-real":
            return _run_real_pack_command(args)

        if args.command == "universe":
            return _run_universe_command(args)

        parser.error(f"Unknown command: {args.command}")
        return 2

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def _run_packs_command(args: argparse.Namespace) -> int:
    from pymercator.cli_packs import run_packs_command

    return run_packs_command(args)


def _run_prices_command(args: argparse.Namespace) -> int:
    from pymercator.cli_prices import run_prices_command

    return run_prices_command(args)


def _run_universe_command(args: argparse.Namespace) -> int:
    from pymercator.cli_universe import run_universe_command

    return run_universe_command(args)


def _resolve_output_paths(
    output: str | None,
    json_output: str | None,
    run_dir: str | None,
) -> tuple[str, str, str]:
    return (
        str(output) if output else "",
        str(json_output) if json_output else "",
        str(run_dir) if run_dir else "",
    )


if __name__ == "__main__":
    raise SystemExit(main())
