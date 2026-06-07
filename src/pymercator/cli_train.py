from __future__ import annotations

import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pymercator import train_detail_report as train_detail_report_mod
from pymercator.artifact_metadata import artifact_metadata
from pymercator.horizon_observer import (
    dominance_strength,
    horizon_alignment,
    horizon_spread,
)
from pymercator.legacy_prediction_engines import (
    SKLEARN_AVAILABLE,
)
from pymercator.prediction_config import effective_prediction_config, horizon_key
from pymercator.prediction_lab import run_prediction_lab
from pymercator.ui import color_metric, colorize, muted_line, strip_ansi

ENGINE_ALIASES = {
}

EXPERIMENTAL_ENGINE_NAMES = {
    "histgradientboosting",
    "logistic_elasticnet",
    "sgd_logloss_calibrated",
    "adaboost",
}
REAL_ENGINES = {
    "extratrees",
    "randomforest",
    "gradientboosting",
    *EXPERIMENTAL_ENGINE_NAMES,
    "ridge_ensemble",
}
BENCHMARK_ENGINES = [
    "extratrees",
    "randomforest",
    "gradientboosting",
    "histgradientboosting",
    "logistic_elasticnet",
    "sgd_logloss_calibrated",
    "adaboost",
]
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



# ---------------------------------------------------------------------------
# AURUM Etapa 4.1
# Normalize feature metadata from evaluation payloads.
# Prefer canonical training metadata produced by legacy_prediction_engines.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# AURUM Etapa 4.1
# Force canonical feature metadata on final train payloads.
# This is a final payload normalizer; it does not alter model predictions.
# ---------------------------------------------------------------------------

def _aurum_force_payload_canonical_features(payload):
    if not isinstance(payload, dict):
        return payload

    try:
        from pymercator.features.training_selector import load_canonical_feature_names
        from pymercator.features.groups import is_duplicate_alias

        raw_cols = payload.get("feature_columns") or []

        if not isinstance(raw_cols, list):
            raw_cols = []

        wanted = load_canonical_feature_names()
        canonical_cols = [c for c in wanted if c in raw_cols]

        if not canonical_cols and raw_cols:
            canonical_cols = [c for c in raw_cols if not is_duplicate_alias(c)]

        if not raw_cols:
            return payload

        removed = [c for c in raw_cols if c not in canonical_cols]

        payload["feature_columns_raw"] = list(raw_cols)
        payload["feature_columns"] = list(canonical_cols)
        payload["features_used"] = len(canonical_cols)
        payload["feature_selection_mode"] = "canonical_final_payload"
        payload["raw_features"] = len(raw_cols)
        payload["canonical_features"] = len(canonical_cols)
        payload["removed_features"] = len(removed)
        payload["feature_selection"] = {
            "mode": "canonical_final_payload",
            "status": "OK",
            "raw_features": len(raw_cols),
            "canonical_features": len(canonical_cols),
            "removed_features": len(removed),
            "removed": removed,
        }

    except Exception as exc:
        payload["feature_selection_mode"] = "canonical_final_payload_failed"
        payload["feature_selection_error"] = str(exc)

    return payload

def _aurum_feature_metadata_from_evaluation(payload):
    if not isinstance(payload, dict):
        return {}

    fs = payload.get("feature_selection")
    if isinstance(fs, dict):
        columns = payload.get("feature_columns") or fs.get("canonical") or []
        return {
            "feature_selection": fs,
            "feature_selection_mode": payload.get("feature_selection_mode") or fs.get("mode"),
            "features_used": payload.get("features_used") or fs.get("canonical_features") or len(columns),
            "feature_columns": columns,
            "raw_features": payload.get("raw_features") or fs.get("raw_features"),
            "canonical_features": payload.get("canonical_features") or fs.get("canonical_features"),
            "removed_features": payload.get("removed_features") or fs.get("removed_features"),
        }

    out = {}
    for key in (
        "feature_selection_mode",
        "features_used",
        "feature_columns",
        "raw_features",
        "canonical_features",
        "removed_features",
    ):
        if key in payload:
            out[key] = payload.get(key)

    return out


def _aurum_apply_canonical_feature_metadata(target, source):
    if not isinstance(target, dict) or not isinstance(source, dict):
        return target

    meta = _aurum_feature_metadata_from_evaluation(source)

    if not meta:
        return target

    for key, value in meta.items():
        if value is not None:
            target[key] = value

    return target

def engine_availability() -> dict[str, bool]:
    return {
        "sklearn_available": bool(SKLEARN_AVAILABLE),
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

    payload.setdefault("schema_version", "prediction_evaluation.v1")
    payload.setdefault("runtime", artifact_metadata())
    payload.update(metadata)
    payload.setdefault("schema_version", "prediction_evaluation.v1")
    payload.setdefault("runtime", artifact_metadata())
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
    spread = horizon_spread(scores)

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
        "horizon_alignment": horizon_alignment(scores),
        "dominance_strength": dominance_strength(scores),
        "horizon_scores": scores,
        "horizon_spread": spread,
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


# ---------------------------------------------------------------------------
# AURUM Etapa 5
# Adaptive horizon observer.
# Penalizes weak horizons and boosts strong horizons before combined_score.
# ---------------------------------------------------------------------------

_aurum_original_observer_summary = _observer_summary


def _aurum_normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    clean: dict[str, float] = {}

    for key in ("D5", "D20", "D60"):
        try:
            value = float(weights.get(key, 0.0) or 0.0)
        except Exception:
            value = 0.0
        clean[key] = max(0.0, value)

    total = sum(clean.values())

    if total <= 0:
        return {"D5": 0.25, "D20": 0.35, "D60": 0.40}

    return {key: clean[key] / total for key in ("D5", "D20", "D60")}


def _aurum_adaptive_observer_weights(
    scores: dict[str, float],
    base_weights: dict[str, float],
) -> tuple[dict[str, float], dict[str, list[str]]]:
    adjusted: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}

    for hz in ("D5", "D20", "D60"):
        score = float(scores.get(hz, 0.0) or 0.0)
        weight = float(base_weights.get(hz, 0.0) or 0.0)
        hz_reasons: list[str] = []

        # Score aqui Ã© ACC*100. Abaixo de 50 equivale edge negativo.
        if score < 50.0:
            weight *= 0.25
            hz_reasons.append("edge_negative")

        # Muito ruim: praticamente contraindicador.
        if score < 40.0:
            weight *= 0.50
            hz_reasons.append("deep_weak")

        # Levemente positivo, mas ainda nÃ£o forte.
        if 50.0 <= score < 56.0:
            weight *= 0.80
            hz_reasons.append("modest_edge")

        # Forte.
        if score >= 58.0:
            weight *= 1.50
            hz_reasons.append("strong_quality")

        # Muito forte.
        if score >= 62.0:
            weight *= 1.20
            hz_reasons.append("very_strong_quality")

        adjusted[hz] = weight
        reasons[hz] = hz_reasons or ["neutral"]

    return _aurum_normalize_weights(adjusted), reasons


def _observer_summary(*args, **kwargs):
    observer = _aurum_original_observer_summary(*args, **kwargs)

    score_by_horizon = kwargs.get("score_by_horizon")
    observer_config = kwargs.get("observer_config")

    if score_by_horizon is None and args:
        score_by_horizon = args[0]

    if observer_config is None:
        if len(args) >= 2:
            observer_config = args[1]
        else:
            observer_config = {}

    if score_by_horizon is None:
        score_by_horizon = {}

    if observer_config is None:
        observer_config = {}

    if not isinstance(observer, dict):
        return observer

    scores = observer.get("scores") or observer.get("horizon_scores") or score_by_horizon or {}
    if not isinstance(scores, dict):
        return observer

    base_weights = observer.get("weights") or observer_config.get("weights", {})
    if not isinstance(base_weights, dict):
        base_weights = {}

    normalized_base = _aurum_normalize_weights(base_weights)
    adaptive_weights, adjustments = _aurum_adaptive_observer_weights(scores, normalized_base)

    combined_score = round(
        sum(float(scores.get(hz, 0.0) or 0.0) * adaptive_weights.get(hz, 0.0) for hz in ("D5", "D20", "D60")),
        6,
    )

    dominant_horizon = max(scores, key=lambda key: float(scores.get(key, 0.0) or 0.0)) if scores else "-"

    observer["base_weights"] = {
        key: round(value, 6) for key, value in normalized_base.items()
    }
    observer["weights"] = {
        key: round(value, 6) for key, value in adaptive_weights.items()
    }
    observer["adaptive_weights"] = {
        key: round(value, 6) for key, value in adaptive_weights.items()
    }
    observer["observer_adjustments"] = adjustments
    observer["combined_score"] = combined_score
    observer["dominant_horizon"] = dominant_horizon
    observer["mode"] = "adaptive_weighted"

    return observer



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


def _degenerate_metric_warnings(horizon_models: dict[str, Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for horizon, model in horizon_models.items():
        if not isinstance(model, dict):
            continue
        metric_groups: list[tuple[str, dict[str, Any]]] = []
        ensemble_metrics = model.get("ensemble_metrics", {})
        if isinstance(ensemble_metrics, dict):
            metric_groups.append(("ridge_ensemble", ensemble_metrics))
        base_metrics = model.get("base_metrics", {})
        if isinstance(base_metrics, dict):
            metric_groups.extend(
                (str(engine), metrics)
                for engine, metrics in base_metrics.items()
                if isinstance(metrics, dict)
            )

        for engine, metrics in metric_groups:
            try:
                observations = int(metrics.get("observations", 0) or 0)
            except (TypeError, ValueError):
                observations = 0
            if observations <= 0:
                continue
            try:
                predicted_up_rate = float(metrics.get("predicted_up_rate", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
            quality_status = str(metrics.get("quality_status", "")).strip().upper()
            if (
                quality_status == "DEGENERATE"
                or predicted_up_rate > 0.80
                or predicted_up_rate < 0.20
            ):
                warnings.append(
                    {
                        "horizon": str(horizon),
                        "engine": engine,
                        "predicted_up_rate": round(predicted_up_rate, 6),
                        "quality_status": "DEGENERATE",
                        "warning": "DEGENERATE WARNING",
                    }
                )
    return warnings


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

    degenerate_warnings = _degenerate_metric_warnings(horizon_models)
    if degenerate_warnings:
        status = "DEGENERATE"

    return {
        "baseline_accuracy": baseline_accuracy,
        "ensemble_accuracy": ensemble_accuracy,
        "edge": edge,
        "precision": precision,
        "recall": recall,
        "false_positive_rate": false_positive_rate,
        "status": status,
        "quality_status": status,
        "degenerate": bool(degenerate_warnings),
        "degenerate_warnings": degenerate_warnings,
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


def _resolved_train_outputs(
    *,
    dataset_output: str | Path,
    evaluation_output: str | Path,
    is_experimental: bool,
    is_baseline: bool,
) -> tuple[str, str, Path]:
    output = Path(evaluation_output)
    dataset = Path(dataset_output)
    kind = "baseline" if is_baseline else "experimental" if is_experimental else ""

    if not kind or output.name != "latest_evaluation.json":
        return str(dataset), str(output), output.parent

    root = output.parent / kind
    if dataset.name == "latest_dataset.csv":
        resolved_dataset = root / "latest_dataset.csv"
    else:
        resolved_dataset = dataset
    return str(resolved_dataset), str(root / "latest_evaluation.json"), root


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
    by_engine: list[dict[str, Any]] = []
    trials_executed = 0
    total_fits = 0
    cache_used = False
    base_models_retrained = False
    mode = "disabled" if not enabled else "unknown"
    status = "OK"

    for horizon, model in horizon_models.items():
        autotune_payload = model.get("autotune", {})
        audit = autotune_payload.get("audit", {})
        if isinstance(audit, dict) and enabled:
            trials_executed += int(audit.get("trials_executed", 0) or 0)
            total_fits += int(audit.get("total_fits", 0) or 0)
            cache_used = cache_used or bool(audit.get("cache_used", False))
            base_models_retrained = base_models_retrained or bool(
                audit.get("base_models_retrained", False)
            )
            if str(audit.get("mode", "") or "") not in {"", "disabled", "unknown"}:
                mode = str(audit.get("mode"))
            if str(audit.get("status", "OK")).upper() not in {"OK", ""}:
                status = str(audit.get("status")).upper()
        raw_rows = autotune_payload.get("by_engine", [])
        if isinstance(raw_rows, list):
            for row in raw_rows:
                if isinstance(row, dict):
                    item = dict(row)
                    item.setdefault("horizon", str(horizon))
                    by_engine.append(item)
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

    if enabled and trials_executed <= 0:
        status = "WARNING"
    if enabled and mode == "unknown" and by_engine:
        mode = "random_search"
    trials_requested = sum(int(row.get("trials_requested", 0) or 0) for row in by_engine)
    if enabled and trials_requested <= 0:
        trials_requested = int(autotune_iter) * max(1, len(models_tuned or tuned or [])) * max(
            1,
            len(row_count_by_horizon),
        )

    baseline_score = 50.0
    combined_score = 0.0
    edge = 0.0
    improvement: list[dict[str, Any]] = []
    for horizon, model in horizon_models.items():
        metrics = model.get("ensemble_metrics", {})
        if isinstance(metrics, dict):
            accuracy = _as_float(metrics.get("accuracy"), 0.0)
            improvement.append(
                {
                    "metric": f"{horizon}_edge",
                    "before": 0.0,
                    "after": round(accuracy - 0.5, 6),
                    "delta": round(accuracy - 0.5, 6),
                }
            )

    return {
        "enabled": bool(enabled),
        "mode": mode,
        "autotune_iter": int(autotune_iter),
        "autotune_cv": int(autotune_cv),
        "trials_requested": trials_requested if enabled else 0,
        "trials_executed": trials_executed if enabled else 0,
        "cv_splits": int(autotune_cv) if enabled else 0,
        "walk_forward": bool(enabled),
        "total_fits": total_fits if enabled else 0,
        "cache_used": cache_used if enabled else False,
        "base_models_retrained": base_models_retrained if enabled else False,
        "status": status,
        "models_tuned": models_tuned if enabled else [],
        "best_params": tuned if enabled else {},
        "duration_seconds": round(duration_seconds, 4),
        "asset_count": assets,
        "row_count_by_horizon": row_count_by_horizon,
        "by_engine": by_engine if enabled else [],
        "improvement": improvement if enabled else [],
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
    calibration_enabled: bool | None = None,
    calibration_method: str | None = None,
    calibration_cv: int | None = None,
    threshold_metric: str | None = None,
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
            "calibration_enabled": calibration_enabled,
            "calibration_method": calibration_method,
            "calibration_cv": calibration_cv,
            "threshold_metric": threshold_metric,
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
    selected_calibration = dict(config.get("calibration", {}))
    is_experimental = bool(experimental)
    baseline_requested = explicit_engines and selected_engines == ["rolling_majority"]
    dataset_output, evaluation_output, output_root = _resolved_train_outputs(
        dataset_output=dataset_output,
        evaluation_output=evaluation_output,
        is_experimental=is_experimental,
        is_baseline=baseline_requested,
    )
    small_universe_allowed = bool(
        allow_small_universe
        or (is_experimental and experimental_policy.get("allow_small_universe") is True)
    )
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

    valid_train_engines = REAL_ENGINES | BASELINE_ENGINES
    unknown_engines = [engine for engine in selected_engines if engine not in valid_train_engines]
    if explicit_engines and unknown_engines:
        valid_text = ", ".join(["rolling_majority", *sorted(REAL_ENGINES)])
        return {
            "command": "train",
            "horizons": selected_horizons,
            "status": "FAIL",
            "reason": (
                "Unknown prediction engines: "
                f"{', '.join(unknown_engines)}. "
                f"Valid train engines: {valid_text}"
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

    if any(engine in EXPERIMENTAL_ENGINE_NAMES for engine in selected_base_engines):
        is_experimental = True

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
            calibration=selected_calibration,
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
            "schema_version": "prediction_evaluation.v1",
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
            "runtime": artifact_metadata(),
            **availability,
        }
        _write_evaluation_metadata(path=evaluation_output, metadata=metadata)
        return {
            "schema_version": "prediction_evaluation.v1",
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
    feature_metadata: dict[str, Any] = {}

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
        dataset_payload = payload.get("dataset", {})
        if not feature_metadata and dataset_payload.get("feature_set"):
            feature_metadata = {
                "feature_set": dataset_payload.get("feature_set", ""),
                "features_total": dataset_payload.get("features_total", 0),
                "features_used": dataset_payload.get("features_used", 0),
                "feature_groups": dataset_payload.get("feature_groups", {}),
                "feature_selection_summary": dataset_payload.get(
                    "feature_selection_summary",
                    {},
                ),
                "feature_columns": dataset_payload.get("feature_columns", []),
                "feature_audit": dataset_payload.get("feature_audit", ""),
            }
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
            "calibration": evaluation_payload.get("calibration", {}),
            "probability_thresholds": evaluation_payload.get("probability_thresholds", {}),
            "optimal_threshold": evaluation_payload.get("optimal_threshold"),
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
    try:
        baseline_accuracy = float(model_quality.get("baseline_accuracy", 0.5))
    except (TypeError, ValueError):
        baseline_accuracy = 0.5
    try:
        combined_score = float(observer.get("combined_score", 0.0))
    except (TypeError, ValueError):
        combined_score = 0.0
    try:
        model_edge = float(model_quality.get("edge", 0.0))
    except (TypeError, ValueError):
        model_edge = 0.0
    if selected_autotune:
        autotune_payload["improvement"] = [
            {
                "metric": "combined_score",
                "before": round(baseline_accuracy * 100.0, 6),
                "after": round(combined_score, 6),
                "delta": round(combined_score - (baseline_accuracy * 100.0), 6),
            },
            {
                "metric": "edge",
                "before": 0.0,
                "after": round(model_edge, 6),
                "delta": round(model_edge, 6),
            },
            *autotune_payload.get("improvement", []),
        ]
    final_payload = {
        "schema_version": "prediction_evaluation.v1",
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
        "calibration": selected_calibration,
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
            "calibration": selected_calibration,
            "min_history": selected_min_history,
            "min_train_rows": selected_min_train_rows,
            "min_assets": selected_min_assets,
            "min_rows_per_horizon": selected_min_rows_per_horizon,
            "temporal_split": True,
            "shuffle": False,
        },
        "horizon_models": horizon_models,
        "thresholds_by_horizon": {
            key: model.get("optimal_threshold")
            for key, model in horizon_models.items()
            if isinstance(model, dict) and model.get("optimal_threshold") is not None
        },
        "calibration_by_horizon": {
            key: model.get("calibration", {})
            for key, model in horizon_models.items()
            if isinstance(model, dict)
        },
        "horizon_observer": observer,
        "horizon_scores": observer.get("horizon_scores", observer.get("scores", {})),
        "horizon_spread": observer.get("horizon_spread", 0.0),
        "horizon_alignment": observer.get("horizon_alignment", "-"),
        "dominance_strength": observer.get("dominance_strength", "-"),
        "row_count_by_horizon": row_count_by_horizon,
        "asset_count_by_horizon": asset_count_by_horizon,
        "dropped_assets_by_horizon": dropped_assets_by_horizon,
        "model_quality": model_quality,
        "diagnostic": diagnostic,
        "autotune": autotune_payload,
        "autotune_summary": autotune_payload,
        "feature_set": feature_metadata.get("feature_set", ""),
        "features_total": feature_metadata.get("features_total", 0),
        "features_used": feature_metadata.get("features_used", 0),
        "feature_groups": feature_metadata.get("feature_groups", {}),
        "feature_selection_summary": feature_metadata.get("feature_selection_summary", {}),
        "feature_columns": feature_metadata.get("feature_columns", []),
        "feature_audit": feature_metadata.get("feature_audit", ""),
        "rows": total_rows,
        "assets": assets,
        "trained_at": trained_at,
        "metrics": {
            "combined_score": observer.get("combined_score", 0.0),
            "dominant_horizon": observer.get("dominant_horizon", "-"),
            "behavior": observer.get("behavior", "AVOID"),
            "model_quality_status": model_quality.get("status", "WEAK"),
        },
        "runtime": artifact_metadata(),
        **availability,
    }

    if status == "FAIL":
        _write_failed_training_artifacts(
            evaluation_output=evaluation_output,
            payload=final_payload,
        )
        return {
            "schema_version": "prediction_evaluation.v1",
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
            "calibration": selected_calibration,
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
            "thresholds_by_horizon": final_payload["thresholds_by_horizon"],
            "calibration_by_horizon": final_payload["calibration_by_horizon"],
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

    # AURUM Etapa 4.1: prefer canonical feature metadata from horizon evaluations.
    try:
        for _hz_payload in final_payload.get("horizons", {}).values():
            if isinstance(_hz_payload, dict):
                _aurum_apply_canonical_feature_metadata(final_payload, _hz_payload)
                break
        for _hz_payload in final_payload.get("horizon_results", {}).values():
            if isinstance(_hz_payload, dict):
                _aurum_apply_canonical_feature_metadata(final_payload, _hz_payload)
                break
    except Exception:
        pass

    final_payload = _aurum_force_payload_canonical_features(final_payload)
    multi_output.write_text(
        json.dumps(final_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    Path(evaluation_output).parent.mkdir(parents=True, exist_ok=True)
    final_payload = _aurum_force_payload_canonical_features(final_payload)
    Path(evaluation_output).write_text(
        json.dumps(final_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "schema_version": "prediction_evaluation.v1",
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
        "calibration": selected_calibration,
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
        "thresholds_by_horizon": final_payload["thresholds_by_horizon"],
        "calibration_by_horizon": final_payload["calibration_by_horizon"],
        "autotune": autotune_payload,
        "autotune_summary": autotune_payload,
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


def _colored_metric(value: Any, metric: str) -> str:
    if value in {None, ""}:
        return "-"
    return color_metric(value, metric)


def _detail_value(value: Any, metric: str | None = None) -> str:
    if value in {None, ""}:
        return "-"
    if metric:
        return color_metric(value, metric)
    return str(value)


def _detail_kv(label: str, value: Any, metric: str | None = None, width: int = 24) -> str:
    return f"{label:<{width}} {_detail_value(value, metric)}"


def _rate_from_counts(metrics: dict[str, Any], *, positive: str) -> float | None:
    if positive == "false_positive":
        if "false_positive_rate" in metrics:
            return float(metrics["false_positive_rate"])
        numerator = float(metrics.get("false_positive", 0.0) or 0.0)
        denominator = numerator + float(metrics.get("true_negative", 0.0) or 0.0)
    else:
        if "false_negative_rate" in metrics:
            return float(metrics["false_negative_rate"])
        numerator = float(metrics.get("false_negative", 0.0) or 0.0)
        denominator = numerator + float(metrics.get("true_positive", 0.0) or 0.0)
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def _metric_field(metrics: dict[str, Any], key: str) -> Any:
    if key in metrics:
        return metrics[key]
    if key == "false_positive_rate":
        return _rate_from_counts(metrics, positive="false_positive")
    if key == "false_negative_rate":
        return _rate_from_counts(metrics, positive="false_negative")
    return None


def _metric_lines(
    metrics: dict[str, Any],
    *,
    train_rows: int | None = None,
    test_rows: int | None = None,
    baseline_accuracy: float = 0.5,
    include_edge: bool = False,
    include_probability_distribution: bool = True,
    quality_status: str = "",
) -> list[str]:
    rows = [
        ("observations", _metric_field(metrics, "observations"), None),
        ("accuracy", _metric_field(metrics, "accuracy"), "accuracy"),
        ("precision", _metric_field(metrics, "precision"), "precision"),
        ("recall", _metric_field(metrics, "recall"), "recall"),
        (
            "false_positive_rate",
            _metric_field(metrics, "false_positive_rate"),
            "false_positive_rate",
        ),
        (
            "false_negative_rate",
            _metric_field(metrics, "false_negative_rate"),
            "false_negative_rate",
        ),
        ("target_up_rate", _metric_field(metrics, "target_up_rate"), "target_up_rate"),
        (
            "predicted_up_rate",
            _metric_field(metrics, "predicted_up_rate"),
            "predicted_up_rate",
        ),
        ("mae_return", _metric_field(metrics, "mae_return"), "mae_return"),
        ("optimal_threshold", metrics.get("optimal_threshold"), None),
        ("confusion_matrix", _format_confusion(metrics), None),
        (
            "calibrated_probability_stats",
            _format_probability_stats(metrics.get("calibrated_probability_stats", {})),
            None,
        ),
        (
            "quality_status",
            colorize(metrics.get("quality_status", "-"), metrics.get("quality_status", "-")),
            None,
        ),
        ("train_rows", metrics.get("train_rows", train_rows), None),
        ("test_rows", metrics.get("test_rows", test_rows), None),
    ]
    if include_probability_distribution:
        rows.insert(
            13,
            (
                "probability_distribution",
                _format_probability_distribution(metrics.get("probability_distribution", {})),
                None,
            ),
        )
    if "fit_time_seconds" in metrics:
        rows.append(("fit_time_seconds", metrics.get("fit_time_seconds"), None))
    if "predict_time_seconds" in metrics:
        rows.append(("predict_time_seconds", metrics.get("predict_time_seconds"), None))
    if include_edge:
        accuracy = _metric_field(metrics, "accuracy")
        edge = None if accuracy is None else round(float(accuracy) - baseline_accuracy, 6)
        rows.append(("edge_vs_baseline", edge, "edge"))
        if quality_status:
            rows.append(
                (
                    "global_quality_status",
                    colorize(quality_status, quality_status),
                    None,
                )
            )
    return [_detail_kv(label, value, metric) for label, value, metric in rows]


def _coefficient_weights(coefficients: dict[str, Any]) -> dict[str, float]:
    raw = coefficients.get("weights", coefficients.get("coefficients", {}))
    if not isinstance(raw, dict):
        return {}
    weights: dict[str, float] = {}
    for engine, value in raw.items():
        try:
            weights[str(engine)] = float(value)
        except (TypeError, ValueError):
            continue
    return weights


def _normalized_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(abs(value) for value in weights.values())
    if total <= 0:
        return {}
    return {
        engine: round(abs(value) / total, 6)
        for engine, value in weights.items()
    }


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _format_compact_decimal(
    value: Any,
    precision: int,
    *,
    sign: bool = False,
) -> str:
    number = _as_optional_float(value)
    if number is None:
        return "-"
    text = f"{number:+.{precision}f}" if sign else f"{number:.{precision}f}"
    if text.startswith("0."):
        return text[1:]
    if text.startswith("-0."):
        return "-." + text[3:]
    if text.startswith("+0."):
        return "+." + text[3:]
    return text


def _format_score(value: Any) -> str:
    number = _as_optional_float(value)
    return "-" if number is None else f"{number:.2f}"


def _format_weights(weights: dict[str, Any], *, precision: int = 6) -> str:
    if not weights:
        return "-"
    parts = []
    for key, value in weights.items():
        if isinstance(value, int | float):
            parts.append(f"{key}={_format_compact_decimal(value, precision)}")
        else:
            parts.append(f"{key}={value}")
    return " ".join(parts)


def _format_confusion(metrics: dict[str, Any]) -> str:
    matrix = metrics.get("confusion_matrix", {})
    if not isinstance(matrix, dict):
        matrix = {}
    tp = matrix.get("TP", metrics.get("TP", metrics.get("true_positive", 0)))
    tn = matrix.get("TN", metrics.get("TN", metrics.get("true_negative", 0)))
    fp = matrix.get("FP", metrics.get("FP", metrics.get("false_positive", 0)))
    fn = matrix.get("FN", metrics.get("FN", metrics.get("false_negative", 0)))
    return f"TP={tp} TN={tn} FP={fp} FN={fn}"


def _format_probability_stats(stats: dict[str, Any]) -> str:
    if not isinstance(stats, dict) or not stats:
        return "-"
    keys = ("mean", "std", "p05", "p50", "p95", "min", "max")
    return " ".join(f"{key}={stats.get(key, '-')}" for key in keys)


def _format_probability_distribution(distribution: dict[str, Any]) -> str:
    if not isinstance(distribution, dict) or not distribution:
        return "-"
    return " ".join(f"{key}={value}" for key, value in distribution.items())


def _ridge_response_lines(model: dict[str, Any]) -> list[str]:
    coefficients = model.get("ridge_coefficients", {})
    if not isinstance(coefficients, dict):
        coefficients = {}
    weights = _coefficient_weights(coefficients)
    normalized = coefficients.get("normalized_weights")
    if not isinstance(normalized, dict):
        normalized = _normalized_weights(weights)
    alpha = coefficients.get("alpha")
    if alpha is None:
        alpha = (
            model.get("autotune", {})
            .get("tuned_params", {})
            .get("ridge_ensemble", {})
            .get("params", {})
            .get("alpha", 1.0)
        )
    strongest = max(weights, key=lambda key: abs(weights[key])) if weights else "-"
    weakest = min(weights, key=lambda key: abs(weights[key])) if weights else "-"
    return [
        _detail_kv("ridge_coefficients", _format_weights(weights)),
        _detail_kv("intercept", coefficients.get("intercept", "-")),
        _detail_kv("alpha", alpha),
        _detail_kv("normalized_weights", _format_weights(normalized)),
        _detail_kv("strongest_engine", strongest),
        _detail_kv("weakest_engine", weakest),
    ]


def _horizon_sort_key(key: str) -> int:
    try:
        return int(str(key).upper().removeprefix("D"))
    except ValueError:
        return 999


def _detail_report_kv(
    label: str,
    value: Any,
    *,
    status: Any = None,
    width: int = 17,
) -> str:
    text = "-" if value in {None, ""} else str(value)
    if status is not None:
        text = colorize(text, status)
    return f"{label:<{width}} {text}"


def _table_cell(
    value: Any,
    width: int,
    *,
    align: str = "<",
    status: Any = None,
) -> str:
    text = "-" if value in {None, ""} else str(value)
    padded = f"{text:>{width}}" if align == ">" else f"{text:<{width}}"
    return colorize(padded, status) if status is not None else padded


def _table_lines(
    title: str,
    columns: list[tuple[str, int, str]],
    rows: list[list[tuple[Any, Any | None] | Any]],
) -> list[str]:
    lines = [
        title,
        muted_line(),
        " ".join(
            _table_cell(label, width, align=align)
            for label, width, align in columns
        ),
    ]
    for row in rows:
        cells = []
        for column, value in zip(columns, row, strict=False):
            _label, width, align = column
            status = None
            cell_value = value
            if isinstance(value, tuple) and len(value) == 2:
                cell_value, status = value
            cells.append(_table_cell(cell_value, width, align=align, status=status))
        lines.append(" ".join(cells))
    return lines


def _horizon_items(horizon_models: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    items: list[tuple[str, dict[str, Any]]] = []
    for horizon in sorted(horizon_models, key=_horizon_sort_key):
        model = horizon_models.get(horizon, {})
        if isinstance(model, dict):
            items.append((str(horizon), model))
    return items


def _detail_horizons(payload: dict[str, Any], horizon_models: dict[str, Any]) -> list[str]:
    raw_horizons = payload.get("horizons", [])
    if isinstance(raw_horizons, list) and raw_horizons:
        return [horizon_key(item) for item in raw_horizons]
    return [horizon for horizon, _model in _horizon_items(horizon_models)]


def _detail_assets(
    payload: dict[str, Any],
    asset_count_by_horizon: dict[str, Any],
) -> Any:
    if payload.get("assets") not in {None, ""}:
        return payload.get("assets")
    values = [_as_int(value) for value in asset_count_by_horizon.values()]
    return max(values) if values else "-"


def _model_ensemble_metrics(model: dict[str, Any]) -> dict[str, Any]:
    metrics = model.get("ensemble_metrics", {})
    return metrics if isinstance(metrics, dict) else {}


def _model_base_metrics(model: dict[str, Any]) -> dict[str, Any]:
    metrics = model.get("base_metrics", {})
    return metrics if isinstance(metrics, dict) else {}


def _model_threshold(model: dict[str, Any], metrics: dict[str, Any]) -> Any:
    if model.get("optimal_threshold") not in {None, ""}:
        return model.get("optimal_threshold")
    if metrics.get("optimal_threshold") not in {None, ""}:
        return metrics.get("optimal_threshold")
    thresholds = model.get("probability_thresholds", {})
    if isinstance(thresholds, dict):
        for key in ("ridge_ensemble", "ensemble", "threshold"):
            if thresholds.get(key) not in {None, ""}:
                return thresholds.get(key)
    return "-"


def _metric_edge(metrics: dict[str, Any], baseline_accuracy: float) -> float | None:
    accuracy = _as_optional_float(_metric_field(metrics, "accuracy"))
    if accuracy is None:
        return None
    return round(accuracy - baseline_accuracy, 6)


def _edge_read(edge: float | None) -> str:
    if edge is None:
        return "-"
    if edge > 0.02:
        return "GOOD"
    if edge > 0:
        return "THIN EDGE"
    if edge >= -0.005:
        return "NO EDGE"
    return "BAD"


def _edge_read_status(read: str) -> str:
    if read == "GOOD":
        return "OK"
    if read in {"THIN EDGE", "NO EDGE"}:
        return "WATCH"
    if read == "BAD":
        return "FAIL"
    return "-"


def _horizon_quality(metrics: dict[str, Any], edge: float | None) -> str:
    metric_quality = str(metrics.get("quality_status", "") or "").strip().upper()
    if metric_quality == "DEGENERATE":
        return "DEGENERATE"
    accuracy = _as_float(_metric_field(metrics, "accuracy"))
    model_edge = _as_float(edge)
    if accuracy >= 0.58 and model_edge >= 0.08:
        return "STRONG"
    if accuracy >= 0.52 and model_edge >= 0.02:
        return "OK"
    return "WEAK"


def _scoreboard_data(
    *,
    horizon_models: dict[str, Any],
    asset_count_by_horizon: dict[str, Any],
    baseline_accuracy: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for horizon, model in _horizon_items(horizon_models):
        metrics = _model_ensemble_metrics(model)
        edge = _metric_edge(metrics, baseline_accuracy)
        read = _edge_read(edge)
        quality = _horizon_quality(metrics, edge)
        rows.append(
            {
                "horizon": horizon,
                "rows": _as_int(model.get("rows")),
                "assets": asset_count_by_horizon.get(horizon, "-"),
                "threshold": _model_threshold(model, metrics),
                "accuracy": _metric_field(metrics, "accuracy"),
                "edge": edge,
                "predicted_up_rate": _metric_field(metrics, "predicted_up_rate"),
                "target_up_rate": _metric_field(metrics, "target_up_rate"),
                "quality": quality,
                "read": read,
            }
        )
    return rows


def _scoreboard_lines(rows: list[dict[str, Any]]) -> list[str]:
    table_rows: list[list[tuple[Any, Any | None] | Any]] = []
    for row in rows:
        read = str(row["read"])
        table_rows.append(
            [
                row["horizon"],
                row["rows"],
                row["assets"],
                _format_compact_decimal(row["threshold"], 4),
                _format_compact_decimal(row["accuracy"], 4),
                _format_compact_decimal(row["edge"], 4, sign=True),
                _format_compact_decimal(row["predicted_up_rate"], 4),
                _format_compact_decimal(row["target_up_rate"], 4),
                (row["quality"], row["quality"]),
                (read, _edge_read_status(read)),
            ]
        )
    return _table_lines(
        "HORIZON SCOREBOARD",
        [
            ("HZ", 4, "<"),
            ("ROWS", 7, ">"),
            ("ASSETS", 6, ">"),
            ("THRESH", 7, ">"),
            ("ACC", 7, ">"),
            ("EDGE", 8, ">"),
            ("P_UP", 7, ">"),
            ("TARGET", 7, ">"),
            ("QUALITY", 8, "<"),
            ("READ", 10, "<"),
        ],
        table_rows,
    )


def _engine_abbrev(engine: str) -> str:
    aliases = {
        "extratrees": "ET",
        "randomforest": "RF",
        "gradientboosting": "GB",
    }
    return aliases.get(engine.lower(), engine.upper())


def _ridge_weight_payload(model: dict[str, Any]) -> tuple[dict[str, float], dict[str, float]]:
    coefficients = model.get("ridge_coefficients", {})
    if not isinstance(coefficients, dict):
        coefficients = {}
    raw = _coefficient_weights(coefficients)
    normalized = coefficients.get("normalized_weights")
    if isinstance(normalized, dict):
        display: dict[str, float] = {}
        for engine, value in normalized.items():
            parsed = _as_optional_float(value)
            if parsed is not None:
                display[str(engine)] = parsed
    else:
        display = _normalized_weights(raw)
    return raw, display


def _ridge_read(strongest: str, display_weights: dict[str, float]) -> str:
    if not strongest or strongest == "-":
        return "-"
    if display_weights:
        ignored = min(display_weights, key=lambda key: display_weights[key])
        if display_weights.get(ignored, 0.0) <= 0.05:
            return f"{_engine_abbrev(ignored)} IGNORED"
    return f"{_engine_abbrev(strongest)} LEADS"


def _ridge_weight_lines(
    *,
    horizon_models: dict[str, Any],
    base_engines: list[str],
) -> list[str]:
    engines = list(base_engines)
    if not engines:
        seen: list[str] = []
        for _horizon, model in _horizon_items(horizon_models):
            _raw, display = _ridge_weight_payload(model)
            for engine in display:
                if engine not in seen:
                    seen.append(engine)
        engines = seen

    columns: list[tuple[str, int, str]] = [("HZ", 4, "<")]
    columns.extend((engine.upper(), max(8, len(engine.upper())), ">") for engine in engines)
    columns.extend([("STRONGEST", 16, "<"), ("READ", 12, "<")])

    rows: list[list[tuple[Any, Any | None] | Any]] = []
    for horizon, model in _horizon_items(horizon_models):
        raw, display = _ridge_weight_payload(model)
        strongest_source = raw or display
        strongest = (
            max(strongest_source, key=lambda key: abs(strongest_source[key]))
            if strongest_source
            else "-"
        )
        read = _ridge_read(strongest, display)
        row: list[tuple[Any, Any | None] | Any] = [horizon]
        row.extend(_format_compact_decimal(display.get(engine), 3) for engine in engines)
        row.extend([strongest, read])
        rows.append(row)

    return _table_lines("RIDGE WEIGHTS", columns, rows)


def _probability_stats(metrics: dict[str, Any]) -> dict[str, Any]:
    stats = metrics.get("calibrated_probability_stats", {})
    return stats if isinstance(stats, dict) else {}


def _probability_read(
    *,
    stats: dict[str, Any],
    predicted_up_rate: Any,
    target_up_rate: Any,
) -> str:
    p_up = _as_optional_float(predicted_up_rate)
    target = _as_optional_float(target_up_rate)
    if p_up is not None and target is not None:
        if p_up > target + 0.07:
            return "BIASED_UP"
        if p_up < target - 0.07:
            return "BIASED_DOWN"

    std = _as_optional_float(stats.get("std"))
    p05 = _as_optional_float(stats.get("p05"))
    p95 = _as_optional_float(stats.get("p95"))
    if std is not None and p05 is not None and p95 is not None:
        if std < 0.02 and (p95 - p05) < 0.08:
            return "COMPRESSED"
        return "BALANCED"

    return "-"


def _probability_profile_data(horizon_models: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for horizon, model in _horizon_items(horizon_models):
        metrics = _model_ensemble_metrics(model)
        stats = _probability_stats(metrics)
        p_up = _metric_field(metrics, "predicted_up_rate")
        target = _metric_field(metrics, "target_up_rate")
        rows.append(
            {
                "horizon": horizon,
                "mean": stats.get("mean"),
                "std": stats.get("std"),
                "p05": stats.get("p05"),
                "p50": stats.get("p50"),
                "p95": stats.get("p95"),
                "predicted_up_rate": p_up,
                "target_up_rate": target,
                "read": _probability_read(
                    stats=stats,
                    predicted_up_rate=p_up,
                    target_up_rate=target,
                ),
            }
        )
    return rows


def _probability_profile_lines(rows: list[dict[str, Any]]) -> list[str]:
    table_rows: list[list[tuple[Any, Any | None] | Any]] = []
    for row in rows:
        read = str(row["read"])
        table_rows.append(
            [
                row["horizon"],
                _format_compact_decimal(row["mean"], 3),
                _format_compact_decimal(row["std"], 3),
                _format_compact_decimal(row["p05"], 3),
                _format_compact_decimal(row["p50"], 3),
                _format_compact_decimal(row["p95"], 3),
                _format_compact_decimal(row["predicted_up_rate"], 3),
                (read, read),
            ]
        )
    return _table_lines(
        "PROBABILITY PROFILE",
        [
            ("HZ", 4, "<"),
            ("MEAN", 6, ">"),
            ("STD", 6, ">"),
            ("P05", 6, ">"),
            ("P50", 6, ">"),
            ("P95", 6, ">"),
            ("P_UP", 6, ">"),
            ("READ", 12, "<"),
        ],
        table_rows,
    )


def _confusion_counts(metrics: dict[str, Any]) -> dict[str, int]:
    matrix = metrics.get("confusion_matrix", {})
    if not isinstance(matrix, dict):
        matrix = {}
    return {
        "TP": _as_int(matrix.get("TP", metrics.get("TP", metrics.get("true_positive", 0)))),
        "TN": _as_int(matrix.get("TN", metrics.get("TN", metrics.get("true_negative", 0)))),
        "FP": _as_int(matrix.get("FP", metrics.get("FP", metrics.get("false_positive", 0)))),
        "FN": _as_int(matrix.get("FN", metrics.get("FN", metrics.get("false_negative", 0)))),
    }


def _confusion_read(*, edge: float | None, fpr: float | None, fnr: float | None) -> str:
    if fpr is not None and fpr > 0.60:
        return "TOO_MANY_FP"
    if fnr is not None and fnr > 0.60:
        return "TOO_MANY_FN"
    return "OK" if edge is not None and edge > 0 else "WEAK"


def _confusion_summary_data(
    *,
    horizon_models: dict[str, Any],
    baseline_accuracy: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for horizon, model in _horizon_items(horizon_models):
        metrics = _model_ensemble_metrics(model)
        counts = _confusion_counts(metrics)
        fpr = _as_optional_float(_metric_field(metrics, "false_positive_rate"))
        fnr = _as_optional_float(_metric_field(metrics, "false_negative_rate"))
        edge = _metric_edge(metrics, baseline_accuracy)
        rows.append(
            {
                "horizon": horizon,
                **counts,
                "fpr": fpr,
                "fnr": fnr,
                "read": _confusion_read(edge=edge, fpr=fpr, fnr=fnr),
            }
        )
    return rows


def _confusion_summary_lines(rows: list[dict[str, Any]]) -> list[str]:
    table_rows: list[list[tuple[Any, Any | None] | Any]] = []
    for row in rows:
        read = str(row["read"])
        table_rows.append(
            [
                row["horizon"],
                row["TP"],
                row["TN"],
                row["FP"],
                row["FN"],
                _format_compact_decimal(row["fpr"], 4),
                _format_compact_decimal(row["fnr"], 4),
                (read, read),
            ]
        )
    return _table_lines(
        "CONFUSION SUMMARY",
        [
            ("HZ", 4, "<"),
            ("TP", 7, ">"),
            ("TN", 7, ">"),
            ("FP", 7, ">"),
            ("FN", 7, ">"),
            ("FPR", 7, ">"),
            ("FNR", 7, ">"),
            ("READ", 12, "<"),
        ],
        table_rows,
    )


def _observer_detail_lines(observer: dict[str, Any]) -> list[str]:
    scores = observer.get("scores", {})
    weights = observer.get("weights", {})
    if not isinstance(scores, dict):
        scores = {}
    if not isinstance(weights, dict):
        weights = {}

    lines = ["OBSERVER", muted_line()]
    for horizon in sorted(scores, key=_horizon_sort_key):
        lines.append(_detail_report_kv(f"{horizon} score", _format_score(scores.get(horizon))))
    lines.extend(
        [
            _detail_report_kv("weights", _format_weights(weights, precision=3)),
            _detail_report_kv(
                "combined_score",
                _format_compact_decimal(observer.get("combined_score"), 4),
            ),
            _detail_report_kv("dominant", observer.get("dominant_horizon", "-")),
            _detail_report_kv(
                "behavior",
                observer.get("behavior", "-"),
                status=observer.get("behavior", "-"),
            ),
            _detail_report_kv(
                "alignment",
                observer.get("horizon_alignment", "-"),
                status=observer.get("horizon_alignment", "-"),
            ),
            _detail_report_kv(
                "dominance",
                observer.get("dominance_strength", "-"),
                status=observer.get("dominance_strength", "-"),
            ),
        ]
    )
    return lines


def _probability_distribution_lines(horizon_models: dict[str, Any]) -> list[str]:
    lines = ["PROBABILITY DISTRIBUTION", muted_line()]
    for horizon, model in _horizon_items(horizon_models):
        metrics = _model_ensemble_metrics(model)
        lines.append(
            _detail_report_kv(
                f"{horizon} probability_distribution",
                _format_probability_distribution(metrics.get("probability_distribution", {})),
                width=29,
            )
        )
    return lines


def _base_engine_metric_lines(
    *,
    horizon_models: dict[str, Any],
    base_engines: list[str],
    baseline_accuracy: float,
    include_probability_distribution: bool,
) -> list[str]:
    lines = ["BASE ENGINE METRICS", muted_line()]
    for horizon, model in _horizon_items(horizon_models):
        rows = _as_int(model.get("rows"))
        test_rows = _as_int(model.get("evaluated_rows"))
        train_rows = max(0, rows - test_rows)
        metrics_by_engine = _model_base_metrics(model)
        engines = base_engines or sorted(metrics_by_engine)
        for engine in engines:
            metrics = metrics_by_engine.get(engine, {})
            if not isinstance(metrics, dict):
                metrics = {}
            lines.append(f"{horizon} {engine}")
            lines.extend(
                _metric_lines(
                    metrics,
                    train_rows=train_rows,
                    test_rows=test_rows,
                    baseline_accuracy=baseline_accuracy,
                    include_probability_distribution=include_probability_distribution,
                )
            )
            lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _ensemble_metric_lines(
    *,
    horizon_models: dict[str, Any],
    baseline_accuracy: float,
    model_quality_status: str,
    include_probability_distribution: bool,
) -> list[str]:
    lines = ["RIDGE / ENSEMBLE METRICS", muted_line()]
    for horizon, model in _horizon_items(horizon_models):
        rows = _as_int(model.get("rows"))
        test_rows = _as_int(model.get("evaluated_rows"))
        train_rows = max(0, rows - test_rows)
        metrics = _model_ensemble_metrics(model)
        lines.append(horizon)
        lines.extend(
            _metric_lines(
                metrics,
                train_rows=train_rows,
                test_rows=test_rows,
                baseline_accuracy=baseline_accuracy,
                include_edge=True,
                include_probability_distribution=include_probability_distribution,
                quality_status=model_quality_status,
            )
        )
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _ridge_response_detail_lines(horizon_models: dict[str, Any]) -> list[str]:
    lines = ["RIDGE RESPONSE", muted_line()]
    for horizon, model in _horizon_items(horizon_models):
        lines.append(horizon)
        lines.extend(_ridge_response_lines(model))
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _format_duration(seconds: Any) -> str:
    total = max(0, int(round(_as_float(seconds, 0.0))))
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _yes_no(value: Any) -> str:
    return "YES" if bool(value) else "NO"


def _autotune_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("autotune_summary", payload.get("autotune", {}))
    return raw if isinstance(raw, dict) else {}


def _autotune_summary_lines(
    payload: dict[str, Any],
    *,
    horizons: list[str],
    base_engines: list[str],
) -> list[str]:
    autotune = _autotune_payload(payload)
    if not autotune.get("enabled"):
        return []
    rows = [
        ("enabled", str(bool(autotune.get("enabled"))).lower()),
        ("mode", autotune.get("mode", "unknown")),
        ("trials_requested", autotune.get("trials_requested", 0)),
        ("trials_executed", autotune.get("trials_executed", 0)),
        ("cv_splits", autotune.get("cv_splits", autotune.get("autotune_cv", "-"))),
        ("walk_forward", _yes_no(autotune.get("walk_forward", True))),
        ("horizons", ",".join(horizons) or "-"),
        ("engines", ",".join(base_engines) or "-"),
        ("total_fits", autotune.get("total_fits", 0)),
        ("cache_used", _yes_no(autotune.get("cache_used", False))),
        ("base_models_retrained", str(bool(autotune.get("base_models_retrained", False))).lower()),
        ("elapsed_time", _format_duration(autotune.get("duration_seconds", autotune.get("elapsed_seconds", 0)))),
        ("status", autotune.get("status", "OK")),
    ]
    return [
        "AUTOTUNE SUMMARY",
        muted_line(),
        *[
            _detail_report_kv(label, value, status=value if label == "status" else None)
            for label, value in rows
        ],
    ]


def _autotune_by_engine_lines(payload: dict[str, Any]) -> list[str]:
    autotune = _autotune_payload(payload)
    rows = autotune.get("by_engine", [])
    if not autotune.get("enabled") or not isinstance(rows, list):
        return []
    table_rows: list[list[tuple[Any, Any | None] | Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        table_rows.append(
            [
                row.get("horizon", "-"),
                row.get("engine", "-"),
                row.get("trials", 0),
                _format_compact_decimal(row.get("best_acc"), 4),
                _format_compact_decimal(row.get("best_edge"), 4, sign=True),
                _format_compact_decimal(row.get("best_fpr"), 4),
                _format_duration(row.get("time_seconds", 0)),
                _format_weights(row.get("best_params", {}), precision=3),
            ]
        )
    if not table_rows:
        return []
    return _table_lines(
        "AUTOTUNE BY ENGINE",
        [
            ("HZ", 4, "<"),
            ("ENGINE", 18, "<"),
            ("TRIALS", 6, ">"),
            ("BEST_ACC", 8, ">"),
            ("BEST_EDGE", 9, ">"),
            ("BEST_FPR", 8, ">"),
            ("TIME", 8, ">"),
            ("BEST_PARAMS", 30, "<"),
        ],
        table_rows,
    )


def _autotune_improvement_lines(payload: dict[str, Any]) -> list[str]:
    autotune = _autotune_payload(payload)
    rows = autotune.get("improvement", [])
    if not autotune.get("enabled") or not isinstance(rows, list):
        return []
    table_rows: list[list[tuple[Any, Any | None] | Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        table_rows.append(
            [
                row.get("metric", "-"),
                _format_compact_decimal(row.get("before"), 4),
                _format_compact_decimal(row.get("after"), 4),
                _format_compact_decimal(row.get("delta"), 4, sign=True),
            ]
        )
    if not table_rows:
        return []
    return _table_lines(
        "AUTOTUNE IMPROVEMENT",
        [
            ("METRIC", 16, "<"),
            ("BEFORE", 10, ">"),
            ("AFTER", 10, ">"),
            ("DELTA", 10, ">"),
        ],
        table_rows,
    )


def _verdict_lines(
    *,
    status: str,
    quality: str,
    behavior: str,
    scoreboard_rows: list[dict[str, Any]],
    probability_rows: list[dict[str, Any]],
    confusion_rows: list[dict[str, Any]],
) -> list[str]:
    lines = ["VERDICT", muted_line()]
    if status in {"OK", "DEGRADED"}:
        lines.append(f"Model executed correctly, but quality is {quality}.")
    else:
        lines.append(f"Model status is {status}; quality is {quality}.")

    prob_reads = {str(row.get("read", "-")) for row in probability_rows}
    if "COMPRESSED" in prob_reads:
        lines.append("Probabilities are calibrated but compressed near 0.50.")
    elif {"BIASED_UP", "BIASED_DOWN"} & prob_reads:
        lines.append("Probability profile shows directional bias.")
    elif "BALANCED" in prob_reads:
        lines.append("Probability profile is balanced across horizons.")
    else:
        lines.append("Probability profile is unavailable for one or more horizons.")

    positive_edges = [
        row
        for row in scoreboard_rows
        if _as_float(row.get("edge")) > 0
    ]
    high_fp_horizons = {
        str(row.get("horizon"))
        for row in confusion_rows
        if str(row.get("read")) == "TOO_MANY_FP"
    }
    if positive_edges:
        best = max(positive_edges, key=lambda row: _as_float(row.get("edge")))
        horizon = str(best.get("horizon", "-"))
        edge_read = str(best.get("read", "-"))
        edge_descriptor = {
            "GOOD": "good",
            "THIN EDGE": "thin",
        }.get(edge_read, edge_read.lower())
        if horizon in high_fp_horizons:
            lines.append(
                f"{horizon} has {edge_descriptor} positive edge, "
                "but false positives remain high."
            )
        else:
            lines.append(f"{horizon} has {edge_descriptor} positive edge.")
    else:
        lines.append("No horizon shows enough positive edge for actionable use.")

    if quality in {"WEAK", "DEGENERATE"} or behavior == "AVOID":
        lines.append("Do not allow actionable trades unless regime and model quality improve.")
    else:
        lines.append("Allow action only with policy gates and regime confirmation.")
    return lines


def render_train_detail_report(
    payload: dict[str, Any],
    *,
    include_engines: bool = False,
    include_prob_dist: bool = False,
    full: bool = False,
) -> str:
    quality = payload.get("model_quality", {})
    if not isinstance(quality, dict):
        quality = {}
    observer = payload.get("horizon_observer", {})
    if not isinstance(observer, dict):
        observer = {}
    horizon_models = payload.get("horizon_models", {})
    if not isinstance(horizon_models, dict):
        horizon_models = {}
    asset_count_by_horizon = payload.get("asset_count_by_horizon", {})
    if not isinstance(asset_count_by_horizon, dict):
        asset_count_by_horizon = {}
    base_engines = [
        str(engine)
        for engine in payload.get("base_engines", [])
        if str(engine).strip()
    ]
    horizons = _detail_horizons(payload, horizon_models)
    model_quality_status = str(quality.get("status", "-") or "-").upper()
    baseline_accuracy = _as_float(quality.get("baseline_accuracy", 0.5), 0.5)
    status = str(payload.get("status", "-") or "-").upper()
    behavior = str(observer.get("behavior", "-") or "-").upper()

    scoreboard_rows = _scoreboard_data(
        horizon_models=horizon_models,
        asset_count_by_horizon=asset_count_by_horizon,
        baseline_accuracy=baseline_accuracy,
    )
    probability_rows = _probability_profile_data(horizon_models)
    confusion_rows = _confusion_summary_data(
        horizon_models=horizon_models,
        baseline_accuracy=baseline_accuracy,
    )

    lines = [
        "PYMERCATOR TRAIN DETAIL",
        muted_line(),
        "",
        "GLOBAL SUMMARY",
        muted_line(),
        _detail_report_kv("engine", payload.get("engine_used", "-")),
        _detail_report_kv("status", status, status=status),
        _detail_report_kv("quality", model_quality_status, status=model_quality_status),
        _detail_report_kv(
            "edge",
            _format_compact_decimal(quality.get("edge", "-"), 4, sign=True),
        ),
        _detail_report_kv("behavior", behavior, status=behavior),
        _detail_report_kv("assets", _detail_assets(payload, asset_count_by_horizon)),
        _detail_report_kv("horizons", ",".join(horizons) or "-"),
        _detail_report_kv("models", ",".join(base_engines) or "-"),
        _detail_report_kv("combiner", payload.get("meta_model", "-")),
        _detail_report_kv("observer", observer.get("mode", payload.get("observer_mode", "-"))),
    ]
    if model_quality_status == "DEGENERATE":
        lines.extend(
            [
                _detail_report_kv(
                    "DEGENERATE WARNING",
                    colorize("base probability outputs are degenerate", "DEGENERATE"),
                    width=20,
                ),
                _detail_report_kv(
                    "degenerate_models",
                    len(quality.get("degenerate_warnings", []) or []),
                    width=20,
                ),
            ]
        )

    sections = []
    for autotune_section in (
        _autotune_summary_lines(payload, horizons=horizons, base_engines=base_engines),
        _autotune_by_engine_lines(payload),
        _autotune_improvement_lines(payload),
    ):
        if autotune_section:
            sections.append(autotune_section)

    sections.extend([
        _scoreboard_lines(scoreboard_rows),
        _ridge_weight_lines(horizon_models=horizon_models, base_engines=base_engines),
        _probability_profile_lines(probability_rows),
        _confusion_summary_lines(confusion_rows),
    ])

    if include_engines or full:
        sections.append(
            _base_engine_metric_lines(
                horizon_models=horizon_models,
                base_engines=base_engines,
                baseline_accuracy=baseline_accuracy,
                include_probability_distribution=include_prob_dist or full,
            )
        )
    if include_prob_dist or full:
        sections.append(_probability_distribution_lines(horizon_models))
    if full:
        sections.append(_ridge_response_detail_lines(horizon_models))
        sections.append(
            _ensemble_metric_lines(
                horizon_models=horizon_models,
                baseline_accuracy=baseline_accuracy,
                model_quality_status=model_quality_status,
                include_probability_distribution=True,
            )
        )

    sections.extend(
        [
            _observer_detail_lines(observer),
            _verdict_lines(
                status=status,
                quality=model_quality_status,
                behavior=behavior,
                scoreboard_rows=scoreboard_rows,
                probability_rows=probability_rows,
                confusion_rows=confusion_rows,
            ),
        ]
    )
    for section in sections:
        lines.extend(["", *section])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# AURUM Etapa 4.1 visual wrapper
# Inserts FEATURE SELECTION into train --details without touching table builders.
# ---------------------------------------------------------------------------

_aurum_original_train_detail_renderer = render_train_detail_report


def _aurum_feature_selection_visual_lines() -> list[str]:
    try:
        import json as _json
        from pathlib import Path as _Path

        p = _Path("storage/prediction/latest_multi_horizon_evaluation.json")
        data = _json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        data = {}

    selection = data.get("feature_selection") if isinstance(data, dict) else {}
    if not isinstance(selection, dict):
        selection = {}

    mode = data.get("feature_selection_mode") or selection.get("mode") or "unknown"
    raw_features = data.get("raw_features") or selection.get("raw_features") or data.get("features_used") or 0
    canonical_features = data.get("canonical_features") or selection.get("canonical_features") or data.get("features_used") or 0
    removed_features = data.get("removed_features") or selection.get("removed_features") or 0
    removed = selection.get("removed") or []
    if not isinstance(removed, list):
        removed = []

    lines = [
        "FEATURE SELECTION",
        "-" * 80,
        f"{'mode':<20} {mode}",
        f"{'raw_features':<20} {raw_features}",
        f"{'canonical_features':<20} {canonical_features}",
        f"{'removed_features':<20} {removed_features}",
    ]

    if removed:
        shown = ", ".join(str(x) for x in removed[:12])
        if len(removed) > 12:
            shown += ", ..."
        lines.append(f"{'removed':<20} {shown}")

    return lines


def render_train_detail_report(*args, **kwargs):
    rendered = _aurum_original_train_detail_renderer(*args, **kwargs)

    block = "\n".join(_aurum_feature_selection_visual_lines()) + "\n\n"

    if isinstance(rendered, str):
        if "FEATURE SELECTION" in rendered:
            return rendered
        if "HORIZON SCOREBOARD" in rendered:
            return rendered.replace("HORIZON SCOREBOARD", block + "HORIZON SCOREBOARD", 1)
        return rendered + "\n\n" + block.rstrip()

    if isinstance(rendered, list):
        if any(str(x) == "FEATURE SELECTION" for x in rendered):
            return rendered
        for i, item in enumerate(rendered):
            if str(item) == "HORIZON SCOREBOARD":
                return rendered[:i] + _aurum_feature_selection_visual_lines() + [""] + rendered[i:]
        return rendered + [""] + _aurum_feature_selection_visual_lines()

    return rendered



def _load_train_detail_payload(path: str | Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except Exception:
        payload = fallback.get("payload", fallback)
    return payload if isinstance(payload, dict) else fallback


def _engine_available_for_benchmark(engine: str) -> bool:
    if engine in BENCHMARK_ENGINES:
        return bool(SKLEARN_AVAILABLE)
    return False


def _benchmark_keep(row: dict[str, Any]) -> str:
    if row.get("status") != "OK":
        return "NO"
    return "YES" if _as_float(row.get("avg_edge")) > 0 else "NO"


def render_engine_benchmark(payload: dict[str, Any]) -> str:
    rows = payload.get("rows", [])
    lines = [
        "ENGINE BENCHMARK",
        muted_line(),
        (
            f"{'ENGINE':<22} {'D5_EDGE':>8} {'D20_EDGE':>8} {'D60_EDGE':>8} "
            f"{'AVG_EDGE':>9} {'FPR':>7} {'BRIER':>7} {'TIME':>8} {'KEEP':>6}"
        ),
    ]
    for row in rows:
        if row.get("status") in {"NOT_AVAILABLE", "FAIL"}:
            lines.append(
                f"{row.get('engine', '-'):<22} {row.get('status', '-'):>42} {'NO':>6}"
            )
            continue
        lines.append(
            f"{row.get('engine', '-'):<22} "
            f"{_format_compact_decimal(row.get('D5_edge'), 4, sign=True):>8} "
            f"{_format_compact_decimal(row.get('D20_edge'), 4, sign=True):>8} "
            f"{_format_compact_decimal(row.get('D60_edge'), 4, sign=True):>8} "
            f"{_format_compact_decimal(row.get('avg_edge'), 4, sign=True):>9} "
            f"{_format_compact_decimal(row.get('fpr'), 4):>7} "
            f"{_format_compact_decimal(row.get('brier_score'), 4):>7} "
            f"{_format_duration(row.get('time_seconds', 0)):>8} "
            f"{row.get('keep', '-'):<6}"
        )
    return "\n".join(lines)


def run_train_benchmark_engines(args: Any) -> int:
    started_at = time.perf_counter()
    config = effective_prediction_config(
        path=getattr(args, "config", "config/prediction.json"),
        overrides={
            "horizons": getattr(args, "horizons", ""),
            "min_history": getattr(args, "min_history", None),
            "min_train_rows": getattr(args, "min_train_rows", None),
            "n_jobs": getattr(args, "n_jobs", None),
        },
    )
    horizons = [int(item) for item in config.get("horizons", [5, 20, 60])]
    training = config.get("training", {})
    selected_min_history = int(training.get("min_history", 120))
    selected_min_train_rows = int(training.get("min_train_rows", 100))
    selected_n_jobs = max(1, int(training.get("n_jobs", 4)))
    output = Path(
        str(
            getattr(
                args,
                "benchmark_output",
                "storage/prediction/latest_engine_benchmark.json",
            )
            or "storage/prediction/latest_engine_benchmark.json"
        )
    )
    work_root = output.parent / "engine_benchmark"
    available_engines = [
        engine for engine in BENCHMARK_ENGINES if _engine_available_for_benchmark(engine)
    ]
    rows_by_engine: dict[str, dict[str, Any]] = {
        engine: {
            "engine": engine,
            "status": "OK" if engine in available_engines else "NOT_AVAILABLE",
            "reason": "" if engine in available_engines else "sklearn engine not available",
            "time_seconds": 0.0,
        }
        for engine in BENCHMARK_ENGINES
    }

    if available_engines:
        for horizon in horizons:
            key = horizon_key(horizon)
            horizon_dir = work_root / key.lower()
            try:
                payload = run_prediction_lab(
                    matrix=getattr(args, "matrix", "storage/features/latest_feature_matrix.csv"),
                    prices_dir=getattr(args, "prices_dir", "data/prices"),
                    dataset_output=horizon_dir / "latest_dataset.csv",
                    evaluation_output=horizon_dir / "latest_evaluation.json",
                    horizon=horizon,
                    min_history=selected_min_history,
                    min_train_rows=selected_min_train_rows,
                    engines=["ridge_ensemble"],
                    base_engines=available_engines,
                    n_jobs=selected_n_jobs,
                    autotune=False,
                    calibration=config.get("calibration", {}),
                )
                evaluation = payload.get("evaluation", {})
                metrics_by_engine = evaluation.get("base_metrics", {})
                engine_status = evaluation.get("engine_status", {})
                ridge_weights = (
                    evaluation.get("ridge_coefficients", {})
                    .get("weights", {})
                    if isinstance(evaluation.get("ridge_coefficients", {}), dict)
                    else {}
                )
                timing_by_engine = {
                    str(item.get("engine")): float(item.get("time_seconds", 0.0) or 0.0)
                    for item in evaluation.get("autotune", {}).get("by_engine", [])
                    if isinstance(item, dict)
                }
                for engine in available_engines:
                    status = str(engine_status.get(engine, "OK"))
                    if status not in {"", "OK"}:
                        rows_by_engine[engine]["status"] = "FAIL"
                        rows_by_engine[engine]["reason"] = status
                    metrics = metrics_by_engine.get(engine, {})
                    if not isinstance(metrics, dict):
                        metrics = {}
                    accuracy = _as_float(metrics.get("accuracy"), 0.0)
                    rows_by_engine[engine][f"{key}_edge"] = round(accuracy - 0.5, 6)
                    for field, metric_key in [
                        ("_accuracy", "accuracy"),
                        ("_balanced_accuracy", "balanced_accuracy"),
                        ("_auc", "auc"),
                        ("_brier_scores", "brier_score"),
                        ("_fnrs", "false_negative_rate"),
                        ("_p_ups", "predicted_up_rate"),
                        ("_target_rates", "target_up_rate"),
                        ("_calibration_errors", "calibration_error"),
                    ]:
                        value = _as_optional_float(metrics.get(metric_key))
                        if value is not None:
                            rows_by_engine[engine].setdefault(field, []).append(value)
                    rows_by_engine[engine].setdefault("_fprs", []).append(
                        _as_float(metrics.get("false_positive_rate"), 0.0)
                    )
                    ridge_weight = _as_optional_float(ridge_weights.get(engine))
                    if ridge_weight is not None:
                        rows_by_engine[engine].setdefault("_ridge_weights", []).append(
                            ridge_weight
                        )
                    rows_by_engine[engine]["time_seconds"] += timing_by_engine.get(engine, 0.0)
            except Exception as exc:
                for engine in available_engines:
                    rows_by_engine[engine]["status"] = "FAIL"
                    rows_by_engine[engine]["reason"] = str(exc)

    rows: list[dict[str, Any]] = []
    average_fields = {
        "_accuracy": "accuracy",
        "_balanced_accuracy": "balanced_accuracy",
        "_auc": "auc",
        "_brier_scores": "brier_score",
        "_fnrs": "fnr",
        "_p_ups": "p_up",
        "_target_rates": "target_rate",
        "_calibration_errors": "calibration_error",
        "_ridge_weights": "ridge_weight",
    }
    for engine in BENCHMARK_ENGINES:
        row = dict(rows_by_engine[engine])
        edges = [
            _as_float(row.get(f"D{horizon}_edge"), 0.0)
            for horizon in horizons
            if row.get(f"D{horizon}_edge") is not None
        ]
        row["avg_edge"] = round(sum(edges) / len(edges), 6) if edges else 0.0
        fprs = row.pop("_fprs", [])
        row["fpr"] = round(sum(fprs) / len(fprs), 6) if fprs else 0.0
        for private_key, public_key in average_fields.items():
            values = row.pop(private_key, [])
            row[public_key] = round(sum(values) / len(values), 6) if values else None
        row["keep"] = _benchmark_keep(row)
        rows.append(row)

    payload = {
        "schema_version": "engine_benchmark.v1",
        "status": "OK",
        "horizons": horizons,
        "engines": BENCHMARK_ENGINES,
        "default_operational_engines": [
            "extratrees",
            "randomforest",
            "gradientboosting",
        ],
        "operational_config_changed": False,
        "rows": rows,
        "files": {"output": str(output), "work_root": str(work_root)},
        "elapsed_seconds": round(time.perf_counter() - started_at, 4),
        "runtime": artifact_metadata(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_engine_benchmark(payload))
    return 0


def render_train_summary(payload: dict[str, Any]) -> str:
    status = payload.get("status", "-")
    lines = [f"TRAIN | STATUS {colorize(status, status)}"]

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
        quality_status = model_quality.get("status", "-")
        lines.append(f"- model_quality: {colorize(quality_status, quality_status)}")
        if str(quality_status).upper() == "DEGENERATE":
            lines.append("- DEGENERATE WARNING: base probability outputs are degenerate")
        lines.append(
            "- baseline_accuracy: "
            f"{_colored_metric(model_quality.get('baseline_accuracy'), 'baseline_accuracy')}"
        )
        lines.append(
            "- ensemble_accuracy: "
            f"{_colored_metric(model_quality.get('ensemble_accuracy'), 'ensemble_accuracy')}"
        )
        lines.append(f"- edge: {_colored_metric(model_quality.get('edge'), 'edge')}")
        lines.append(
            f"- precision: {_colored_metric(model_quality.get('precision'), 'precision')}"
        )
        lines.append(f"- recall: {_colored_metric(model_quality.get('recall'), 'recall')}")
        lines.append(
            "- false_positive_rate: "
            f"{_colored_metric(model_quality.get('false_positive_rate'), 'false_positive_rate')}"
        )
    observer = payload.get("horizon_observer", {})
    if observer:
        lines.append(
            f"- combined_score: {_colored_metric(observer.get('combined_score'), 'combined_score')}"
        )
        lines.append(f"- dominant_horizon: {observer.get('dominant_horizon', '-')}")
        behavior = observer.get("behavior", "-")
        lines.append(f"- behavior: {colorize(behavior, behavior)}")

    for key, model in payload.get("horizon_models", {}).items():
        model_status = model.get("status", "-")
        metrics = model.get("ensemble_metrics", {})
        lines.append(
            f"- {key}: {colorize(model_status, model_status)} "
            f"acc={_colored_metric(metrics.get('accuracy'), 'accuracy')} "
            f"prec={_colored_metric(metrics.get('precision'), 'precision')} "
            f"recall={_colored_metric(metrics.get('recall'), 'recall')}"
        )

    observer_status = observer.get("status", "-")
    lines.extend(
        [
            f"- observer: {colorize(observer_status, observer_status)}",
            f"- status: {colorize(status, status)}",
            f"- output: {evaluation.get('output', '-')}",
        ]
    )
    return "\n".join(lines)


def run_train_command(args: Any) -> int:
    if getattr(args, "train_action", "") == "benchmark-engines":
        return run_train_benchmark_engines(args)

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
        calibration_enabled=(
            False if bool(getattr(args, "disable_calibration", False)) else None
        ),
        calibration_method=getattr(args, "calibration_method", None),
        calibration_cv=getattr(args, "calibration_cv", None),
        threshold_metric=getattr(args, "threshold_metric", None),
        experimental=bool(getattr(args, "experimental", False)),
        allow_small_universe=bool(getattr(args, "allow_small_universe", False)),
    )

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif getattr(args, "details", False):
        detail_payload = _load_train_detail_payload(args.evaluation_output, payload)
        include_full = bool(getattr(args, "full", False))
        report = train_detail_report_mod.render_train_detail_report(
            detail_payload,
            include_engines=bool(getattr(args, "detail_engines", False)) or include_full,
            include_prob_dist=bool(getattr(args, "prob_dist", False)) or include_full,
            full=include_full,
        )
        print(report)
        output = str(getattr(args, "output", "") or "").strip()
        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(strip_ansi(report), encoding="utf-8")
    else:
        print(render_train_summary(payload))

    return 0 if payload["status"] in {"OK", "DEGRADED", "BASELINE"} else 1
