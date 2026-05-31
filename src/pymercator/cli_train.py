from __future__ import annotations

import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pymercator.legacy_prediction_engines import (
    CATBOOST_AVAILABLE,
    SKLEARN_AVAILABLE,
    XGBOOST_AVAILABLE,
)
from pymercator.prediction_config import effective_prediction_config, horizon_key
from pymercator.prediction_lab import run_prediction_lab

ENGINE_ALIASES = {
}

REAL_ENGINES = {"extratrees", "randomforest", "gradientboosting", "ridge_ensemble"}
BASELINE_ENGINES = {"rolling_majority"}
PROFILE_IGNORED_WARNING = "WARNING: --profile is ignored by train. Profiles are applied in run."
OPERATIONAL_HORIZON_REASON = (
    "Non-standard horizons require --experimental. "
    "Default operational horizons are D5,D20,D60."
)
OPERATIONAL_ENGINE_REASON = (
    "Operational training requires 3 base engines: "
    "extratrees,randomforest,gradientboosting"
)


def engine_availability() -> dict[str, bool]:
    return {
        "sklearn_available": bool(SKLEARN_AVAILABLE),
        "xgboost_available": bool(XGBOOST_AVAILABLE),
        "catboost_available": bool(CATBOOST_AVAILABLE),
    }


def default_train_engines() -> list[str]:
    return ["ridge_ensemble"]


def parse_engines(value: str) -> list[str]:
    if not value:
        return default_train_engines()

    engines: list[str] = []
    for item in value.split(","):
        engine = item.strip().lower()
        if not engine:
            continue
        engines.append(ENGINE_ALIASES.get(engine, engine))
    return engines or default_train_engines()


def _trained_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _primary_metrics(payload: dict[str, Any], engine_used: str) -> dict[str, Any]:
    models = payload.get("evaluation", {}).get("models", {})
    if isinstance(models, dict) and isinstance(models.get(engine_used), dict):
        return dict(models[engine_used])
    return {}


def _csv_unique_assets(path: str | Path) -> int:
    return len(_csv_asset_set(path))


def _csv_asset_set(path: str | Path) -> set[str]:
    source = Path(path)
    if not source.exists():
        return set()

    with source.open("r", encoding="utf-8-sig", newline="") as file:
        return {
            _normalize_ticker(row.get("ticker", ""))
            for row in csv.DictReader(file)
            if str(row.get("ticker", "")).strip()
        }


def _csv_row_count(path: str | Path) -> int:
    source = Path(path)
    if not source.exists():
        return 0

    with source.open("r", encoding="utf-8-sig", newline="") as file:
        return sum(1 for _row in csv.DictReader(file))


def _normalize_ticker(value: object) -> str:
    ticker = str(value or "").strip().upper()
    return ticker[:-3] if ticker.endswith(".SA") else ticker


def _write_evaluation_metadata(
    *,
    path: str | Path,
    metadata: dict[str, Any],
) -> None:
    output = Path(path)
    payload: dict[str, Any] = {}

    if output.exists():
        payload = json.loads(output.read_text(encoding="utf-8-sig"))

    payload.update(metadata)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _price_file_ticker(path: Path) -> str:
    name = path.stem.upper()
    return _normalize_ticker(name)


def _diagnose_inputs(
    *,
    universe: str,
    matrix: str,
    prices_dir: str,
    min_history: int,
) -> dict[str, Any]:
    universe_assets = _csv_asset_set(universe)
    matrix_assets = _csv_asset_set(matrix)
    price_dir = Path(prices_dir)
    price_files = sorted(price_dir.glob("*.csv")) if price_dir.exists() else []
    valid_price_assets: set[str] = set()

    for price_file in price_files:
        if _csv_row_count(price_file) >= min_history:
            valid_price_assets.add(_price_file_ticker(price_file))

    return {
        "universe_file": universe,
        "universe_assets": len(universe_assets),
        "feature_matrix_file": matrix,
        "feature_matrix_rows": _csv_row_count(matrix),
        "feature_matrix_assets": len(matrix_assets),
        "prices_dir": prices_dir,
        "price_files": len(price_files),
        "valid_price_files": len(valid_price_assets),
        "_asset_sets": {
            "universe": universe_assets,
            "feature_matrix": matrix_assets,
            "valid_prices": valid_price_assets,
        },
    }


def _bottleneck_step(filter_losses: dict[str, int], min_assets: int) -> str:
    visible = {key: int(value) for key, value in filter_losses.items()}
    for key, value in visible.items():
        if value < min_assets:
            return key

    previous_key = ""
    previous_value = 0
    biggest_drop = 0
    biggest_drop_key = ""
    for key, value in visible.items():
        if previous_key:
            drop = previous_value - value
            if drop > biggest_drop:
                biggest_drop = drop
                biggest_drop_key = key
        previous_key = key
        previous_value = value
    return biggest_drop_key or "-"


def _build_training_diagnostic(
    *,
    universe: str,
    matrix: str,
    prices_dir: str,
    min_history: int,
    min_assets: int,
    row_count_by_horizon: dict[str, int],
    asset_count_by_horizon: dict[str, int],
    dataset_assets_by_horizon: dict[str, set[str]],
) -> dict[str, Any]:
    inputs = _diagnose_inputs(
        universe=universe,
        matrix=matrix,
        prices_dir=prices_dir,
        min_history=min_history,
    )
    asset_sets = inputs.pop("_asset_sets")
    horizon_intersection: set[str] = set()
    for assets in dataset_assets_by_horizon.values():
        if not horizon_intersection:
            horizon_intersection = set(assets)
        else:
            horizon_intersection &= assets

    generated_assets = (
        set().union(*dataset_assets_by_horizon.values())
        if dataset_assets_by_horizon
        else set()
    )
    feature_and_price_assets = asset_sets["feature_matrix"] & asset_sets["valid_prices"]
    if asset_sets["universe"]:
        feature_and_price_assets &= asset_sets["universe"]

    filter_losses = {
        "assets_before_filter": len(asset_sets["universe"] or asset_sets["feature_matrix"]),
        "assets_after_feature_matrix": len(asset_sets["feature_matrix"]),
        "assets_after_min_history": len(asset_sets["valid_prices"]),
        "assets_after_target_generation": len(generated_assets),
        "assets_after_join": len(feature_and_price_assets),
        "assets_after_na_drop": min(asset_count_by_horizon.values(), default=0),
        "assets_after_horizon_intersection": len(horizon_intersection),
    }

    return {
        "inputs": inputs,
        "dataset_by_horizon": {
            key: {
                "rows": row_count_by_horizon.get(key, 0),
                "assets": asset_count_by_horizon.get(key, 0),
            }
            for key in sorted(set(row_count_by_horizon) | set(asset_count_by_horizon))
        },
        "filter_losses": filter_losses,
        "bottleneck_step": _bottleneck_step(filter_losses, min_assets),
    }


def _write_failed_training_artifacts(
    *,
    evaluation_output: str | Path,
    payload: dict[str, Any],
) -> None:
    output = Path(evaluation_output)
    diagnostic_output = output.with_name("latest_failed_training_diagnostic.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    diagnostic_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _score_from_metrics(metrics: dict[str, Any]) -> float:
    accuracy = float(metrics.get("accuracy", 0.0) or 0.0)
    return round(accuracy * 100.0 if accuracy <= 1.0 else accuracy, 4)


def _signal(score: float) -> str:
    if score >= 60.0:
        return "strong"
    if score >= 50.0:
        return "neutral"
    return "weak"


def _behavior(score_by_horizon: dict[str, float]) -> str:
    d5 = _signal(score_by_horizon.get("D5", 0.0)) == "strong"
    d20 = _signal(score_by_horizon.get("D20", 0.0)) == "strong"
    d60 = _signal(score_by_horizon.get("D60", 0.0)) == "strong"

    if d5 and d20 and d60:
        return "TREND_CONFIRM"
    if d5 and d20 and not d60:
        return "SWING"
    if d5 and not d20 and not d60:
        return "TACTICAL"
    if not d5 and d20 and d60:
        return "POSITIONAL_SETUP"
    if not d5 and not d20 and d60:
        return "POSITIONAL_EARLY"
    if d5 and not d20 and d60:
        return "DIVERGENT"
    if not d5 and not d20 and not d60:
        return "AVOID"
    return "SWING_WAIT"


def _observer_summary(
    *,
    horizon_models: dict[str, Any],
    observer_config: dict[str, Any],
) -> dict[str, Any]:
    scores = {
        key: _score_from_metrics(model.get("ensemble_metrics", {}))
        for key, model in horizon_models.items()
    }
    weights = {
        str(key).upper(): float(value)
        for key, value in observer_config.get("weights", {}).items()
    }
    if not weights:
        weight = 1.0 / max(1, len(scores))
        weights = {key: weight for key in scores}

    total_weight = sum(weights.get(key, 0.0) for key in scores) or 1.0
    combined_score = round(
        sum(scores[key] * weights.get(key, 0.0) for key in scores) / total_weight,
        4,
    )
    dominant_horizon = max(scores, key=lambda key: scores[key]) if scores else "-"

    return {
        "engine_used": "horizon_observer",
        "mode": observer_config.get("mode", "weighted"),
        "inputs": list(horizon_models),
        "independent_analysis": bool(observer_config.get("independent_analysis", True)),
        "combined_analysis": bool(observer_config.get("combined_analysis", True)),
        "weights": weights,
        "scores": scores,
        "combined_score": combined_score,
        "dominant_horizon": dominant_horizon,
        "behavior": _behavior(scores),
        "behavior_labels": [
            "TACTICAL",
            "SWING",
            "POSITIONAL_SETUP",
            "POSITIONAL_EARLY",
            "TREND_CONFIRM",
            "DIVERGENT",
            "AVOID",
        ],
        "status": "OK" if scores else "FAIL",
    }


def _weighted_metric(
    *,
    horizon_models: dict[str, Any],
    weights: dict[str, float],
    metric: str,
) -> float:
    values: list[tuple[float, float]] = []
    for key, model in horizon_models.items():
        metrics = model.get("ensemble_metrics", {})
        if not isinstance(metrics, dict):
            continue
        if metric not in metrics:
            continue
        values.append((float(metrics.get(metric, 0.0) or 0.0), weights.get(key, 0.0)))

    if not values:
        return 0.0

    total_weight = sum(weight for _value, weight in values) or float(len(values))
    return round(sum(value * (weight or 1.0) for value, weight in values) / total_weight, 6)


def _model_quality(
    *,
    horizon_models: dict[str, Any],
    observer: dict[str, Any],
) -> dict[str, Any]:
    weights = {
        str(key).upper(): float(value)
        for key, value in observer.get("weights", {}).items()
    }
    baseline_accuracy = 0.5
    ensemble_accuracy = _weighted_metric(
        horizon_models=horizon_models,
        weights=weights,
        metric="accuracy",
    )
    precision = _weighted_metric(
        horizon_models=horizon_models,
        weights=weights,
        metric="precision",
    )
    recall = _weighted_metric(
        horizon_models=horizon_models,
        weights=weights,
        metric="recall",
    )

    false_positive_rates: list[tuple[float, float]] = []
    for key, model in horizon_models.items():
        metrics = model.get("ensemble_metrics", {})
        if not isinstance(metrics, dict):
            continue
        false_positive = float(metrics.get("false_positive", 0.0) or 0.0)
        true_negative = float(metrics.get("true_negative", 0.0) or 0.0)
        denominator = false_positive + true_negative
        if denominator <= 0:
            continue
        false_positive_rates.append((false_positive / denominator, weights.get(key, 0.0)))

    if false_positive_rates:
        total_weight = sum(weight for _value, weight in false_positive_rates) or float(
            len(false_positive_rates)
        )
        false_positive_rate = round(
            sum(value * (weight or 1.0) for value, weight in false_positive_rates)
            / total_weight,
            6,
        )
    else:
        false_positive_rate = 0.0

    edge = round(ensemble_accuracy - baseline_accuracy, 6)
    if ensemble_accuracy >= 0.58 and edge >= 0.08 and precision >= 0.55:
        status = "STRONG"
    elif ensemble_accuracy >= 0.52 and edge >= 0.02:
        status = "OK"
    else:
        status = "WEAK"

    return {
        "baseline_accuracy": baseline_accuracy,
        "ensemble_accuracy": ensemble_accuracy,
        "edge": edge,
        "precision": precision,
        "recall": recall,
        "false_positive_rate": false_positive_rate,
        "status": status,
    }


def _price_row_counts_by_asset(prices_dir: str | Path) -> dict[str, int]:
    root = Path(prices_dir)
    if not root.exists():
        return {}

    return {
        _price_file_ticker(path): _csv_row_count(path)
        for path in root.glob("*.csv")
    }


def _dropped_assets_by_horizon(
    *,
    universe: str,
    matrix: str,
    prices_dir: str,
    min_history: int,
    selected_horizons: list[int],
    dataset_assets_by_horizon: dict[str, set[str]],
) -> dict[str, list[dict[str, Any]]]:
    universe_assets = _csv_asset_set(universe)
    matrix_assets = _csv_asset_set(matrix)
    price_rows = _price_row_counts_by_asset(prices_dir)
    expected_assets = universe_assets or matrix_assets
    dropped: dict[str, list[dict[str, Any]]] = {}

    for horizon in selected_horizons:
        key = horizon_key(horizon)
        present = dataset_assets_by_horizon.get(key, set())
        items: list[dict[str, Any]] = []
        for ticker in sorted(expected_assets - present):
            rows = int(price_rows.get(ticker, 0))
            if ticker not in matrix_assets:
                reason = "missing from feature matrix"
            elif rows == 0:
                reason = "missing price file"
            elif rows < min_history:
                reason = f"insufficient price history: rows={rows}, required={min_history}"
            elif rows < min_history + horizon + 1:
                reason = (
                    f"insufficient history for {key}: "
                    f"rows={rows}, required={min_history + horizon + 1}"
                )
            else:
                reason = "no target rows generated"
            items.append({"ticker": ticker, "reason": reason, "price_rows": rows})
        dropped[key] = items

    return dropped


def _multi_horizon_status(horizon_models: dict[str, Any]) -> tuple[str, str]:
    statuses = [str(model.get("status", "FAIL")) for model in horizon_models.values()]
    valid_count = sum(1 for status in statuses if status in {"OK", "DEGRADED"})

    if statuses and all(status == "OK" for status in statuses):
        return "OK", ""
    if valid_count >= 2:
        return "DEGRADED", "one or more horizons failed or degraded"
    return "FAIL", "multi_horizon_ridge requires at least 2 valid horizons"


def _prediction_output_root(evaluation_output: str | Path) -> Path:
    return Path(evaluation_output).parent


def _same_list(left: list[Any], right: list[Any]) -> bool:
    return [str(item).lower() for item in left] == [str(item).lower() for item in right]


def _weights_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    normalized_left = {str(key).upper(): float(value) for key, value in left.items()}
    normalized_right = {str(key).upper(): float(value) for key, value in right.items()}
    return normalized_left == normalized_right


def _invalid_operational_override_reason(
    *,
    selected_horizons: list[int],
    selected_base_engines: list[str],
    selected_meta: str,
    observer: dict[str, Any],
    defaults: dict[str, Any],
) -> str:
    default_horizons = [int(item) for item in defaults.get("horizons", [5, 20, 60])]
    default_base_engines = [str(item) for item in defaults.get("base_engines", [])]
    default_meta = str(defaults.get("meta_model", "ridge")).lower()
    default_observer = str(defaults.get("observer_mode", "weighted")).lower()
    default_weights = {
        str(key).upper(): float(value)
        for key, value in defaults.get("weights", {}).items()
    }

    if selected_horizons != default_horizons:
        return OPERATIONAL_HORIZON_REASON
    if not _same_list(selected_base_engines, default_base_engines):
        return OPERATIONAL_ENGINE_REASON
    if len(selected_base_engines) != 3:
        return OPERATIONAL_ENGINE_REASON
    if selected_meta != default_meta:
        return (
            "Non-standard meta model requires --experimental. "
            f"Default meta model is {default_meta}."
        )
    if str(observer.get("mode", "")).lower() != default_observer:
        return (
            "Non-standard observer requires --experimental. "
            f"Default operational observer is {default_observer}."
        )
    if not _weights_equal(observer.get("weights", {}), default_weights):
        return "Non-standard horizon weights require --experimental."
    return ""


def _autotune_summary(
    *,
    enabled: bool,
    autotune_iter: int,
    autotune_cv: int,
    duration_seconds: float,
    assets: int,
    row_count_by_horizon: dict[str, int],
    horizon_models: dict[str, Any],
) -> dict[str, Any]:
    tuned: dict[str, Any] = {}
    models_tuned: list[str] = []

    for model in horizon_models.values():
        autotune_payload = model.get("autotune", {})
        params_by_engine = autotune_payload.get("tuned_params", {})
        if not isinstance(params_by_engine, dict):
            continue
        for engine, meta in params_by_engine.items():
            if engine == "ridge_ensemble" or not isinstance(meta, dict):
                continue
            if meta.get("enabled") is True and engine not in models_tuned:
                models_tuned.append(engine)
            if meta.get("params"):
                tuned.setdefault(engine, meta.get("params"))

    return {
        "enabled": bool(enabled),
        "autotune_iter": int(autotune_iter),
        "autotune_cv": int(autotune_cv),
        "models_tuned": models_tuned if enabled else [],
        "best_params": tuned if enabled else {},
        "duration_seconds": round(duration_seconds, 4),
        "asset_count": assets,
        "row_count_by_horizon": row_count_by_horizon,
    }


def run_train_flow(
    *,
    profile: str = "",
    horizon: int = 5,
    horizons: list[int] | str | None = None,
    config_path: str = "config/prediction.json",
    matrix: str = "storage/features/latest_feature_matrix.csv",
    universe: str = "data/universes/ibov_live.csv",
    prices_dir: str = "data/prices",
    dataset_output: str = "storage/prediction/latest_dataset.csv",
    evaluation_output: str = "storage/prediction/latest_evaluation.json",
    min_history: int | None = None,
    min_train_rows: int | None = None,
    engines: list[str] | None = None,
    base_engines: list[str] | str | None = None,
    meta_model: str | None = None,
    observer_mode: str | None = None,
    weights: str | dict[str, float] | None = None,
    independent_horizons: bool = False,
    combined_horizons: bool = False,
    explicit_engines: bool = False,
    n_jobs: int | None = None,
    autotune: bool | None = None,
    autotune_iter: int | None = None,
    autotune_cv: int | None = None,
    experimental: bool = False,
    allow_small_universe: bool = False,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    config = effective_prediction_config(
        path=config_path,
        overrides={
            "horizons": horizons,
            "base_engines": base_engines,
            "meta_model": meta_model,
            "observer_mode": observer_mode,
            "weights": weights,
            "independent_horizons": independent_horizons,
            "combined_horizons": combined_horizons,
            "min_history": min_history,
            "min_train_rows": min_train_rows,
            "n_jobs": n_jobs,
            "autotune": autotune,
            "autotune_iter": autotune_iter,
            "autotune_cv": autotune_cv,
        },
    )
    training = config.get("training", {})
    operational_defaults = config.get("operational_defaults", {})
    experimental_policy = config.get("experimental_policy", {})
    selected_horizons = [int(item) for item in config.get("horizons", [horizon])]
    selected_base_engines = [str(item) for item in config.get("base_engines", [])]
    selected_meta = str(config.get("meta_model", "ridge")).lower()
    selected_engines = list(engines or default_train_engines())
    selected_n_jobs = int(training.get("n_jobs", 4))
    selected_min_history = int(training.get("min_history", 120))
    selected_min_train_rows = int(training.get("min_train_rows", 100))
    selected_min_assets = int(config.get("min_assets", 30))
    selected_min_rows_per_horizon = int(config.get("min_rows_per_horizon", 100))
    selected_autotune = bool(training.get("autotune", False))
    selected_autotune_iter = int(training.get("autotune_iter", 20))
    selected_autotune_cv = int(training.get("autotune_cv", 3))
    is_experimental = bool(experimental)
    small_universe_allowed = bool(
        allow_small_universe
        or (is_experimental and experimental_policy.get("allow_small_universe") is True)
    )
    output_root = _prediction_output_root(evaluation_output)
    files = {
        "matrix": matrix,
        "universe": universe,
        "prices_dir": prices_dir,
        "dataset": dataset_output,
        "evaluation": evaluation_output,
        "multi_horizon_evaluation": str(output_root / "latest_multi_horizon_evaluation.json"),
    }

    if not Path(matrix).exists():
        return {
            "command": "train",
            "horizons": selected_horizons,
            "status": "BLOCKED",
            "reason": "feature matrix not found",
            "required": 1,
            "found": 0,
            "files": files,
        }

    if not Path(prices_dir).exists():
        return {
            "command": "train",
            "horizons": selected_horizons,
            "status": "BLOCKED",
            "reason": "prices directory not found",
            "required": 1,
            "found": 0,
            "files": files,
        }

    if allow_small_universe and not is_experimental:
        return {
            "command": "train",
            "horizons": selected_horizons,
            "status": "FAIL",
            "reason": "--allow-small-universe requires --experimental",
            "operational": True,
            "experimental": False,
            "files": files,
        }

    if selected_meta != "ridge":
        return {
            "command": "train",
            "horizons": selected_horizons,
            "status": "FAIL",
            "reason": f"unsupported meta model: {selected_meta}",
            "files": files,
        }

    baseline_requested = explicit_engines and selected_engines == ["rolling_majority"]
    valid_train_engines = REAL_ENGINES | BASELINE_ENGINES
    unknown_engines = [engine for engine in selected_engines if engine not in valid_train_engines]
    if explicit_engines and unknown_engines:
        return {
            "command": "train",
            "horizons": selected_horizons,
            "status": "FAIL",
            "reason": (
                "Unknown prediction engines: "
                f"{', '.join(unknown_engines)}. "
                "Valid train engines: rolling_majority, extratrees, "
                "randomforest, gradientboosting, ridge_ensemble"
            ),
            "files": files,
        }
    if explicit_engines and "rolling_majority" in selected_engines and not baseline_requested:
        return {
            "command": "train",
            "horizons": selected_horizons,
            "status": "FAIL",
            "reason": "rolling_majority cannot be mixed with real engines",
            "files": files,
        }

    if explicit_engines and not baseline_requested:
        selected_base_engines = [
            engine
            for engine in selected_engines
            if engine in REAL_ENGINES and engine != "ridge_ensemble"
        ] or selected_base_engines

    observer_config = config.get("observer", {})
    if not is_experimental and not baseline_requested:
        reason = _invalid_operational_override_reason(
            selected_horizons=selected_horizons,
            selected_base_engines=selected_base_engines,
            selected_meta=selected_meta,
            observer=observer_config,
            defaults=operational_defaults,
        )
        if reason:
            return {
                "command": "train",
                "horizons": selected_horizons,
                "status": "FAIL",
                "reason": reason,
                "operational": True,
                "experimental": False,
                "files": files,
            }

    availability = engine_availability()

    def run_lab(
        *,
        selected_horizon: int,
        selected: list[str],
        selected_dataset_output: str,
        selected_evaluation_output: str,
    ) -> dict[str, Any]:
        return run_prediction_lab(
            matrix=matrix,
            prices_dir=prices_dir,
            dataset_output=selected_dataset_output,
            evaluation_output=selected_evaluation_output,
            horizon=selected_horizon,
            min_history=selected_min_history,
            min_train_rows=selected_min_train_rows,
            engines=selected,
            base_engines=selected_base_engines,
            n_jobs=max(1, int(selected_n_jobs)),
            autotune=selected_autotune,
            autotune_iter=selected_autotune_iter,
            autotune_cv=selected_autotune_cv,
        )

    if baseline_requested:
        try:
            payload = run_lab(
                selected_horizon=selected_horizons[0],
                selected=["rolling_majority"],
                selected_dataset_output=dataset_output,
                selected_evaluation_output=evaluation_output,
            )
        except Exception as exc:
            return {
                "command": "train",
                "horizons": selected_horizons,
                "status": "FAIL",
                "reason": str(exc),
                "detail": {"error": str(exc)},
                "files": files,
            }

        dataset_rows = int(payload.get("dataset", {}).get("rows", 0))
        evaluation_payload = payload.get("evaluation", {})
        assets = _csv_unique_assets(dataset_output)
        engine_used = str(evaluation_payload.get("engine_used") or "rolling_majority")
        trained_at = _trained_at()
        metrics = _primary_metrics(payload, engine_used)
        metadata = {
            "engine_used": engine_used,
            "is_baseline": True,
            "status": "BASELINE",
            "operational": False,
            "experimental": is_experimental,
            "horizons": [selected_horizons[0]],
            "rows": dataset_rows,
            "assets": assets,
            "trained_at": trained_at,
            "metrics": metrics,
            "training": {
                "n_jobs": selected_n_jobs,
                "autotune": selected_autotune,
                "autotune_iter": selected_autotune_iter,
                "autotune_cv": selected_autotune_cv,
                "min_history": selected_min_history,
                "min_train_rows": selected_min_train_rows,
            },
            **availability,
        }
        _write_evaluation_metadata(path=evaluation_output, metadata=metadata)
        return {
            "command": "train",
            "horizons": [selected_horizons[0]],
            "status": "BASELINE",
            "engine_used": engine_used,
            "is_baseline": True,
            "operational": False,
            "experimental": is_experimental,
            "base_engines": [],
            "meta_model": "",
            "observer": {},
            "training": metadata["training"],
            "dataset": {"rows": dataset_rows, "assets": assets, "output": dataset_output},
            "evaluation": {
                "engine_used": engine_used,
                "is_baseline": True,
                "metrics": metrics,
                "output": evaluation_output,
            },
            "files": files,
        }

    horizon_models: dict[str, Any] = {}
    row_count_by_horizon: dict[str, int] = {}
    asset_count_by_horizon: dict[str, int] = {}
    dataset_assets_by_horizon: dict[str, set[str]] = {}
    total_rows = 0
    assets = 0

    for selected_horizon in selected_horizons:
        key = horizon_key(selected_horizon)
        horizon_dir = output_root / key.lower()
        horizon_dataset = horizon_dir / "latest_dataset.csv"
        horizon_evaluation = horizon_dir / "latest_evaluation.json"
        try:
            payload = run_lab(
                selected_horizon=selected_horizon,
                selected=["ridge_ensemble"],
                selected_dataset_output=str(horizon_dataset),
                selected_evaluation_output=str(horizon_evaluation),
            )
        except Exception as exc:
            horizon_models[key] = {
                "engine_used": "ridge_ensemble",
                "base_engines": selected_base_engines,
                "meta_model": selected_meta,
                "status": "FAIL",
                "reason": str(exc),
                "output": str(horizon_evaluation),
            }
            continue

        evaluation_payload = payload.get("evaluation", {})
        dataset_rows = int(payload.get("dataset", {}).get("rows", 0))
        row_count_by_horizon[key] = dataset_rows
        total_rows += dataset_rows
        horizon_assets = _csv_asset_set(horizon_dataset)
        dataset_assets_by_horizon[key] = horizon_assets
        asset_count_by_horizon[key] = len(horizon_assets)
        assets = max(assets, len(horizon_assets))
        horizon_models[key] = {
            "engine_used": evaluation_payload.get("engine_used", "ridge_ensemble"),
            "base_engines": evaluation_payload.get("base_engines", selected_base_engines),
            "valid_base_engines": evaluation_payload.get("valid_base_engines", []),
            "failed_engines": evaluation_payload.get("failed_engines", []),
            "meta_model": evaluation_payload.get("meta_model", selected_meta),
            "base_metrics": evaluation_payload.get("base_metrics", {}),
            "ridge_coefficients": evaluation_payload.get("ridge_coefficients", {}),
            "ensemble_metrics": evaluation_payload.get("ensemble_metrics", {}),
            "autotune": evaluation_payload.get("autotune", {}),
            "status": evaluation_payload.get("status", payload.get("status", "OK")),
            "reason": evaluation_payload.get("reason", ""),
            "dataset_output": str(horizon_dataset),
            "output": str(horizon_evaluation),
            "rows": int(evaluation_payload.get("rows", 0)),
            "evaluated_rows": int(evaluation_payload.get("evaluated_rows", 0)),
        }

    status, reason = _multi_horizon_status(horizon_models)
    observer = _observer_summary(
        horizon_models=horizon_models,
        observer_config=config.get("observer", {}),
    )
    model_quality = _model_quality(
        horizon_models=horizon_models,
        observer=observer,
    )
    dropped_assets_by_horizon = _dropped_assets_by_horizon(
        universe=universe,
        matrix=matrix,
        prices_dir=prices_dir,
        min_history=selected_min_history,
        selected_horizons=selected_horizons,
        dataset_assets_by_horizon=dataset_assets_by_horizon,
    )
    diagnostic = _build_training_diagnostic(
        universe=universe,
        matrix=matrix,
        prices_dir=prices_dir,
        min_history=selected_min_history,
        min_assets=selected_min_assets,
        row_count_by_horizon=row_count_by_horizon,
        asset_count_by_horizon=asset_count_by_horizon,
        dataset_assets_by_horizon=dataset_assets_by_horizon,
    )

    required_keys = {
        horizon_key(item)
        for item in operational_defaults.get("horizons", [5, 20, 60])
    }
    generated_keys = set(horizon_models)
    if not small_universe_allowed and assets < selected_min_assets:
        status = "FAIL"
        reason = "insufficient assets for operational training"
    elif not small_universe_allowed and any(
        asset_count_by_horizon.get(key, 0) < selected_min_assets
        for key in generated_keys
    ):
        status = "FAIL"
        reason = "insufficient assets for operational training"
    elif not is_experimental and generated_keys != required_keys:
        status = "FAIL"
        reason = "operational training requires D5,D20,D60 horizon models"
    elif any(
        row_count_by_horizon.get(key, 0) < selected_min_rows_per_horizon
        for key in generated_keys
    ):
        status = "FAIL"
        reason = "insufficient rows for operational training"
    else:
        for key, model in horizon_models.items():
            if len(model.get("valid_base_engines", [])) < 2:
                status = "FAIL"
                reason = f"insufficient valid base engines for {key}"
                break
        if status != "FAIL" and observer.get("status") != "OK":
            status = "FAIL"
            reason = "multi-horizon observer was not generated"

    trained_at = _trained_at()
    autotune_payload = _autotune_summary(
        enabled=selected_autotune,
        autotune_iter=selected_autotune_iter,
        autotune_cv=selected_autotune_cv,
        duration_seconds=time.perf_counter() - started_at,
        assets=assets,
        row_count_by_horizon=row_count_by_horizon,
        horizon_models=horizon_models,
    )
    final_payload = {
        "engine_used": "multi_horizon_ridge",
        "is_baseline": False,
        "trained_models": ["multi_horizon_ridge"],
        "status": status,
        "reason": reason,
        "operational": not is_experimental,
        "experimental": is_experimental,
        "horizons": selected_horizons,
        "base_engines": selected_base_engines,
        "meta_model": selected_meta,
        "observer_mode": config.get("observer", {}).get("mode", "weighted"),
        "weights": observer.get("weights", {}),
        "min_assets": selected_min_assets,
        "min_rows_per_horizon": selected_min_rows_per_horizon,
        "observer": {
            "mode": config.get("observer", {}).get("mode", "weighted"),
            "independent_analysis": bool(
                config.get("observer", {}).get("independent_analysis", True)
            ),
            "combined_analysis": bool(config.get("observer", {}).get("combined_analysis", True)),
            "weights": observer.get("weights", {}),
        },
        "training": {
            "n_jobs": selected_n_jobs,
            "autotune": selected_autotune,
            "autotune_iter": selected_autotune_iter,
            "autotune_cv": selected_autotune_cv,
            "min_history": selected_min_history,
            "min_train_rows": selected_min_train_rows,
            "min_assets": selected_min_assets,
            "min_rows_per_horizon": selected_min_rows_per_horizon,
            "temporal_split": True,
            "shuffle": False,
        },
        "horizon_models": horizon_models,
        "horizon_observer": observer,
        "row_count_by_horizon": row_count_by_horizon,
        "asset_count_by_horizon": asset_count_by_horizon,
        "dropped_assets_by_horizon": dropped_assets_by_horizon,
        "model_quality": model_quality,
        "diagnostic": diagnostic,
        "autotune": autotune_payload,
        "rows": total_rows,
        "assets": assets,
        "trained_at": trained_at,
        "metrics": {
            "combined_score": observer.get("combined_score", 0.0),
            "dominant_horizon": observer.get("dominant_horizon", "-"),
            "behavior": observer.get("behavior", "AVOID"),
            "model_quality_status": model_quality.get("status", "WEAK"),
        },
        **availability,
    }

    if status == "FAIL":
        _write_failed_training_artifacts(
            evaluation_output=evaluation_output,
            payload=final_payload,
        )
        return {
            "command": "train",
            "horizons": selected_horizons,
            "status": status,
            "reason": reason,
            "engine_used": "multi_horizon_ridge",
            "is_baseline": False,
            "operational": not is_experimental,
            "experimental": is_experimental,
            "base_engines": selected_base_engines,
            "meta_model": selected_meta,
            "observer": final_payload["observer"],
            "horizon_observer": observer,
            "training": final_payload["training"],
            "dataset": {
                "rows": total_rows,
                "assets": assets,
                "min_assets": selected_min_assets,
                "by_horizon": {
                    key: {
                        "rows": row_count_by_horizon.get(key, 0),
                        "assets": asset_count_by_horizon.get(key, 0),
                    }
                    for key in sorted(generated_keys)
                },
                "output": str(output_root),
            },
            "diagnostic": diagnostic,
            "model_quality": model_quality,
            "dropped_assets_by_horizon": dropped_assets_by_horizon,
            "evaluation": {
                "engine_used": "multi_horizon_ridge",
                "status": status,
                "reason": reason,
                "output": evaluation_output,
                "diagnostic_output": str(
                    Path(evaluation_output).with_name("latest_failed_training_diagnostic.json")
                ),
            },
            "horizon_models": horizon_models,
            "files": files,
            "payload": final_payload,
        }

    multi_output = Path(files["multi_horizon_evaluation"])
    multi_output.parent.mkdir(parents=True, exist_ok=True)
    multi_output.write_text(
        json.dumps(final_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    Path(evaluation_output).parent.mkdir(parents=True, exist_ok=True)
    Path(evaluation_output).write_text(
        json.dumps(final_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "command": "train",
        "horizons": selected_horizons,
        "status": status,
        "reason": reason,
        "engine_used": "multi_horizon_ridge",
        "is_baseline": False,
        "trained_models": ["multi_horizon_ridge"],
        "operational": not is_experimental,
        "experimental": is_experimental,
        "base_engines": selected_base_engines,
        "meta_model": selected_meta,
        "observer": final_payload["observer"],
        "horizon_observer": observer,
        "training": final_payload["training"],
        "dataset": {
            "rows": total_rows,
            "assets": assets,
            "min_assets": selected_min_assets,
            "by_horizon": {
                key: {
                    "rows": row_count_by_horizon.get(key, 0),
                    "assets": asset_count_by_horizon.get(key, 0),
                }
                for key in sorted(generated_keys)
            },
            "output": str(output_root),
        },
        "diagnostic": diagnostic,
        "model_quality": model_quality,
        "dropped_assets_by_horizon": dropped_assets_by_horizon,
        "autotune": autotune_payload,
        "evaluation": {
            "engine_used": "multi_horizon_ridge",
            "is_baseline": False,
            "horizons": selected_horizons,
            "base_engines": selected_base_engines,
            "meta_model": selected_meta,
            "status": status,
            "reason": reason,
            "output": evaluation_output,
            "multi_output": str(multi_output),
            "observer": observer.get("status", "-"),
            "model_quality": model_quality,
        },
        "horizon_models": horizon_models,
        "files": files,
        "payload": final_payload,
    }


def render_train_summary(payload: dict[str, Any]) -> str:
    status = payload.get("status", "-")
    lines = [f"TRAIN | STATUS {status}"]

    if status == "BLOCKED":
        lines.extend(
            [
                f"REASON: {payload.get('reason', '-')}",
                f"REQUIRED: {payload.get('required', '-')}",
                f"FOUND: {payload.get('found', '-')}",
            ]
        )
        return "\n".join(lines)

    if status == "FAIL":
        if payload.get("engine_used"):
            lines.append(f"ENGINE: {payload.get('engine_used')}")
        lines.append(f"REASON: {payload.get('reason', '-')}")
        if payload.get("failed_engines"):
            lines.append(f"FAILED_ENGINES: {', '.join(payload.get('failed_engines', []))}")
        dataset = payload.get("dataset", {})
        diagnostic = payload.get("diagnostic", {})
        if dataset:
            lines.extend(
                [
                    "",
                    "DATASET:",
                    f"- assets: {dataset.get('assets', 0)}",
                    f"- min_assets: {dataset.get('min_assets', '-')}",
                ]
            )
            for key, item in dataset.get("by_horizon", {}).items():
                lines.append(f"- {key} rows: {item.get('rows', 0)}")
                lines.append(f"- {key} assets: {item.get('assets', 0)}")
        if diagnostic:
            inputs = diagnostic.get("inputs", {})
            lines.extend(
                [
                    "",
                    "DIAGNOSTIC:",
                    f"- universe_assets: {inputs.get('universe_assets', 0)}",
                    f"- feature_matrix_assets: {inputs.get('feature_matrix_assets', 0)}",
                    f"- bottleneck_step: {diagnostic.get('bottleneck_step', '-')}",
                ]
            )
        return "\n".join(lines)

    if status not in {"OK", "DEGRADED"}:
        if status not in {"FALLBACK", "BASELINE"}:
            lines.append(f"REASON: {payload.get('reason', '-')}")
            return "\n".join(lines)

    dataset = payload.get("dataset", {})
    evaluation = payload.get("evaluation", {})
    training = payload.get("training", {})

    lines.extend(
        [
            f"ENGINE: {payload.get('engine_used', '-')}",
            f"HORIZONS: {','.join(horizon_key(item) for item in payload.get('horizons', []))}",
            f"BASE ENGINES: {','.join(payload.get('base_engines', []))}",
            f"META: {payload.get('meta_model', '-')}",
            f"OBSERVER: {payload.get('observer', {}).get('mode', '-')}",
            f"AUTOTUNE: {'ON' if training.get('autotune') else 'OFF'}",
            f"BASELINE: {str(payload.get('is_baseline', False)).lower()}",
            "",
            "DATASET:",
        ]
    )
    by_horizon = dataset.get("by_horizon", {})
    if by_horizon:
        for key, item in by_horizon.items():
            lines.append(f"- {key} rows: {item.get('rows', 0)}")
            lines.append(f"- {key} assets: {item.get('assets', 0)}")
    else:
        lines.append(f"- rows: {dataset.get('rows', 0)}")
        lines.append(f"- assets: {dataset.get('assets', 0)}")
    lines.extend(
        [
            f"- output: {dataset.get('output', '-')}",
            "",
            "EVALUATION:",
            f"- engine: {payload.get('engine_used', '-')}",
            f"- baseline: {str(payload.get('is_baseline', False)).lower()}",
        ]
    )
    if evaluation.get("base_engines"):
        lines.append(f"- base_engines: {', '.join(evaluation.get('base_engines', []))}")
    if evaluation.get("meta_model"):
        lines.append(f"- meta_model: {evaluation.get('meta_model')}")
    if evaluation.get("failed_engines"):
        lines.append(f"- failed_engines: {', '.join(evaluation.get('failed_engines', []))}")
    model_quality = payload.get("model_quality") or evaluation.get("model_quality") or {}
    if model_quality:
        lines.append(f"- model_quality: {model_quality.get('status', '-')}")
        lines.append(f"- ensemble_accuracy: {model_quality.get('ensemble_accuracy', '-')}")
        lines.append(f"- edge: {model_quality.get('edge', '-')}")
    lines.extend(
        [
            *[
                f"- {key}: {model.get('status', '-')}"
                for key, model in payload.get("horizon_models", {}).items()
            ],
            f"- observer: {payload.get('horizon_observer', {}).get('status', '-')}",
            f"- status: {status}",
            f"- output: {evaluation.get('output', '-')}",
        ]
    )
    return "\n".join(lines)


def run_train_command(args: Any) -> int:
    if str(getattr(args, "profile", "") or "").strip():
        print(PROFILE_IGNORED_WARNING, file=sys.stderr)

    requested_horizons: str | list[int] | None = getattr(args, "horizons", "")
    if not requested_horizons and getattr(args, "horizon", None) is not None:
        requested_horizons = [int(args.horizon)]

    payload = run_train_flow(
        profile=getattr(args, "profile", ""),
        horizon=int(getattr(args, "horizon", 5) or 5),
        horizons=requested_horizons,
        config_path=getattr(args, "config", "config/prediction.json"),
        matrix=args.matrix,
        universe=getattr(args, "universe", "data/universes/ibov_live.csv"),
        prices_dir=args.prices_dir,
        dataset_output=args.dataset_output,
        evaluation_output=args.evaluation_output,
        min_history=getattr(args, "min_history", None),
        min_train_rows=getattr(args, "min_train_rows", None),
        engines=parse_engines(args.engines),
        base_engines=args.engines,
        meta_model=getattr(args, "meta", None),
        observer_mode=getattr(args, "observer", None),
        weights=getattr(args, "weights", None),
        independent_horizons=bool(getattr(args, "independent_horizons", False)),
        combined_horizons=bool(getattr(args, "combined_horizons", False)),
        explicit_engines=bool(str(args.engines or "").strip()),
        n_jobs=getattr(args, "n_jobs", None),
        autotune=getattr(args, "autotune", None),
        autotune_iter=getattr(args, "autotune_iter", None),
        autotune_cv=getattr(args, "autotune_cv", None),
        experimental=bool(getattr(args, "experimental", False)),
        allow_small_universe=bool(getattr(args, "allow_small_universe", False)),
    )

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_train_summary(payload))

    return 0 if payload["status"] in {"OK", "DEGRADED", "BASELINE"} else 1
