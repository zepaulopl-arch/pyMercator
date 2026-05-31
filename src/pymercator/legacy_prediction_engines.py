
from __future__ import annotations

import itertools
import random
from typing import Any

try:
    from sklearn.ensemble import (
        ExtraTreesRegressor,
        GradientBoostingRegressor,
        RandomForestRegressor,
    )
    from sklearn.metrics import mean_absolute_error
    from sklearn.model_selection import TimeSeriesSplit

    SKLEARN_AVAILABLE = True
except Exception:
    ExtraTreesRegressor = None
    GradientBoostingRegressor = None
    RandomForestRegressor = None
    TimeSeriesSplit = None
    mean_absolute_error = None
    SKLEARN_AVAILABLE = False

try:
    from xgboost import XGBRegressor

    XGBOOST_AVAILABLE = True
except Exception:
    XGBRegressor = None
    XGBOOST_AVAILABLE = False

try:
    from catboost import CatBoostRegressor

    CATBOOST_AVAILABLE = True
except Exception:
    CatBoostRegressor = None
    CATBOOST_AVAILABLE = False


BASELINE_ENGINES = ["rolling_majority"]
LEGACY_BASE_ENGINES = ["extratrees", "randomforest", "gradientboosting"]
ARBITER_ENGINES = ["ridge_ensemble"]
VALID_PREDICTION_ENGINES = [
    *BASELINE_ENGINES,
    *LEGACY_BASE_ENGINES,
    *ARBITER_ENGINES,
]
DEFAULT_ENGINES = ["ridge_ensemble"]
LEGACY_ENGINE_ALIASES: dict[str, str] = {}

LEGACY_RETURN_CLIP_LOWER: float = -20.0
LEGACY_RETURN_CLIP_UPPER: float = 20.0
LEGACY_CONSENSUS_DEVIATION_THRESHOLD: float = 0.5

FEATURE_COLUMNS = [
    "return_1d",
    "return_5d",
    "return_20d",
    "volatility_20d",
    "atr_pct",
    "trend_score",
    "momentum_score",
    "news_score",
    "market_trend",
    "market_volatility",
]

AUTOTUNE_SPACES: dict[str, dict[str, list[Any]]] = {
    "xgb": {
        "n_estimators": [60, 120, 180, 240, 300],
        "max_depth": [2, 3, 4, 6, 9],
        "learning_rate": [0.005, 0.02, 0.05, 0.1, 0.2],
        "subsample": [0.7, 0.8, 0.9, 1.0],
        "colsample_bytree": [0.7, 0.8, 0.9, 1.0],
    },
    "catboost": {
        "iterations": [80, 140, 220, 300, 400],
        "depth": [2, 3, 4, 6, 8, 10],
        "learning_rate": [0.005, 0.02, 0.04, 0.08, 0.2],
        "l2_leaf_reg": [1, 3, 5, 7, 9],
    },
    "extratrees": {
        "n_estimators": [24, 40, 60, 100],
        "max_depth": [3, 6, 10, 16, 25, None],
        "min_samples_leaf": [1, 2, 5, 10, 15],
        "max_features": ["sqrt", "log2", None],
    },
    "randomforest": {
        "n_estimators": [24, 40, 60, 100],
        "max_depth": [3, 6, 10, 16, None],
        "min_samples_leaf": [1, 2, 5, 10],
        "max_features": ["sqrt", "log2", None],
    },
    "gradientboosting": {
        "n_estimators": [24, 40, 60, 100],
        "max_depth": [2, 3, 4],
        "learning_rate": [0.02, 0.05, 0.1],
        "subsample": [0.7, 0.9, 1.0],
    },
}


def available_legacy_engines() -> list[str]:
    return VALID_PREDICTION_ENGINES.copy()


def parse_legacy_engines(engines: list[str] | None = None) -> list[str]:
    if not engines:
        return DEFAULT_ENGINES.copy()

    allowed = set(VALID_PREDICTION_ENGINES)
    parsed: list[str] = []
    for engine in engines:
        raw = engine.strip().lower()
        name = LEGACY_ENGINE_ALIASES.get(raw, raw)
        if name and name not in parsed:
            parsed.append(name)
    unknown = [engine for engine in parsed if engine not in allowed]

    if unknown:
        valid = ", ".join(VALID_PREDICTION_ENGINES)
        baselines = ", ".join(BASELINE_ENGINES)
        raise ValueError(
            f"Unknown prediction engines: {', '.join(unknown)}\n"
            f"Valid engines: {valid}\n"
            f"Baselines: {baselines}"
        )

    return parsed


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def _feature_value(row: dict[str, Any], feature: str) -> float:
    if feature == "market_trend":
        return {"DOWN": -1.0, "CHOPPY": 0.0, "UP": 1.0}.get(
            str(row.get(feature, "")).upper(),
            0.0,
        )

    if feature == "market_volatility":
        return {"LOW": -1.0, "NORMAL": 0.0, "HIGH": 1.0}.get(
            str(row.get(feature, "")).upper(),
            0.0,
        )

    return _to_float(row.get(feature), 0.0)


def _feature_vector(row: dict[str, Any]) -> list[float]:
    return [_feature_value(row, feature) for feature in FEATURE_COLUMNS]


def _target_return_values(
    rows: list[dict[str, Any]],
    target_return_column: str,
) -> list[float]:
    return [_to_float(row.get(target_return_column), 0.0) for row in rows]


def _target_up_values(
    rows: list[dict[str, Any]],
    target_up_column: str,
) -> list[int]:
    return [int(_to_float(row.get(target_up_column), 0.0)) for row in rows]


def _median(values: list[float]) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)
    mid = len(ordered) // 2

    if len(ordered) % 2:
        return ordered[mid]

    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _clip_return_value(value: float) -> float:
    return max(LEGACY_RETURN_CLIP_LOWER, min(LEGACY_RETURN_CLIP_UPPER, value))


def apply_consensus_guard(
    predictions: dict[str, float],
    *,
    max_deviation_from_median: float = LEGACY_CONSENSUS_DEVIATION_THRESHOLD,
) -> dict[str, float]:
    if not predictions:
        return {}

    median = _median(list(predictions.values()))
    guarded: dict[str, float] = {}

    for engine, value in predictions.items():
        guarded_value = median if abs(value - median) > max_deviation_from_median else value
        guarded[engine] = _clip_return_value(guarded_value)

    return guarded


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    augmented = [row.copy() + [vector[index]] for index, row in enumerate(matrix)]

    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            augmented[column][column] += 1e-8
            pivot = column

        if pivot != column:
            augmented[column], augmented[pivot] = augmented[pivot], augmented[column]

        divisor = augmented[column][column] or 1e-8
        for item in range(column, size + 1):
            augmented[column][item] /= divisor

        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor == 0:
                continue
            for item in range(column, size + 1):
                augmented[row][item] -= factor * augmented[column][item]

    return [augmented[row][size] for row in range(size)]


class StableRidgeArbiter:
    def __init__(self, alpha: float = 1.0):
        self.alpha = float(alpha)
        self.intercept = 0.0
        self.weights: list[float] = []

    def fit(self, x_rows: list[list[float]], y_values: list[float]) -> None:
        if not x_rows or not y_values:
            self.intercept = 0.0
            self.weights = []
            return

        width = len(x_rows[0]) + 1
        matrix = [[0.0 for _column in range(width)] for _row in range(width)]
        vector = [0.0 for _row in range(width)]

        for row, target in zip(x_rows, y_values, strict=True):
            values = [1.0, *[float(value) for value in row]]
            for i in range(width):
                vector[i] += values[i] * float(target)
                for j in range(width):
                    matrix[i][j] += values[i] * values[j]

        for index in range(1, width):
            matrix[index][index] += self.alpha

        solution = _solve_linear_system(matrix, vector)

        self.intercept = float(solution[0])
        self.weights = [float(value) for value in solution[1:]]

    def predict_one(self, values: list[float]) -> float:
        if not self.weights:
            return float(self.intercept)

        return float(
            self.intercept
            + sum(
                weight * value
                for weight, value in zip(self.weights, values, strict=True)
            )
        )


def _engine_defaults(engine: str) -> dict[str, Any]:
    if engine == "xgb":
        return {
            "n_estimators": 140,
            "max_depth": 3,
            "learning_rate": 0.05,
            "subsample": 0.9,
            "colsample_bytree": 0.9,
        }

    if engine == "catboost":
        return {
            "iterations": 220,
            "depth": 4,
            "learning_rate": 0.04,
            "loss_function": "MAE",
        }

    if engine == "extratrees":
        return {
            "n_estimators": 24,
            "max_depth": 10,
            "min_samples_leaf": 2,
            "max_features": None,
        }

    if engine == "randomforest":
        return {
            "n_estimators": 24,
            "max_depth": 10,
            "min_samples_leaf": 2,
            "max_features": "sqrt",
        }

    if engine == "gradientboosting":
        return {
            "n_estimators": 24,
            "max_depth": 3,
            "learning_rate": 0.05,
            "subsample": 0.9,
        }

    raise ValueError(f"Unknown legacy engine: {engine}")


def _make_model(
    engine: str,
    params: dict[str, Any],
    *,
    n_jobs: int = 4,
) -> Any:
    if engine == "xgb":
        if not XGBOOST_AVAILABLE or XGBRegressor is None:
            return None

        return XGBRegressor(
            **params,
            objective="reg:squarederror",
            random_state=42,
            n_jobs=n_jobs,
        )

    if engine == "catboost":
        if not CATBOOST_AVAILABLE or CatBoostRegressor is None:
            return None

        return CatBoostRegressor(
            **params,
            random_seed=42,
            thread_count=n_jobs,
            verbose=False,
        )

    if engine == "extratrees":
        if not SKLEARN_AVAILABLE or ExtraTreesRegressor is None:
            return None

        return ExtraTreesRegressor(
            **params,
            random_state=42,
            n_jobs=n_jobs,
        )

    if engine == "randomforest":
        if not SKLEARN_AVAILABLE or RandomForestRegressor is None:
            return None

        return RandomForestRegressor(
            **params,
            random_state=42,
            n_jobs=n_jobs,
        )

    if engine == "gradientboosting":
        if not SKLEARN_AVAILABLE or GradientBoostingRegressor is None:
            return None

        return GradientBoostingRegressor(
            **params,
            random_state=42,
        )

    raise ValueError(f"Unknown legacy engine: {engine}")


def _candidate_param_sets(
    engine: str,
    *,
    n_iter: int = 15,
) -> list[dict[str, Any]]:
    defaults = _engine_defaults(engine)
    space = AUTOTUNE_SPACES.get(engine, {})

    if not space:
        return [defaults]

    keys = list(space)
    all_candidates = [
        dict(zip(keys, values, strict=True))
        for values in itertools.product(*(space[key] for key in keys))
    ]

    rng = random.Random(42)
    rng.shuffle(all_candidates)

    selected = all_candidates[: max(1, int(n_iter))]
    merged: list[dict[str, Any]] = [defaults]

    for candidate in selected:
        item = defaults.copy()
        item.update(candidate)
        merged.append(item)

    unique: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in merged:
        key = repr(sorted(item.items()))
        if key not in seen:
            unique.append(item)
            seen.add(key)

    return unique


def _cv_mae(
    engine: str,
    x_train: list[list[float]],
    y_train: list[float],
    params: dict[str, Any],
    *,
    cv: int = 3,
    n_jobs: int = 4,
) -> float:
    if len(x_train) < max(10, cv + 2):
        return 0.0

    if TimeSeriesSplit is None or mean_absolute_error is None:
        return 0.0

    splits = TimeSeriesSplit(n_splits=max(2, int(cv)))
    errors: list[float] = []

    for train_idx, test_idx in splits.split(x_train):
        model = _make_model(engine, params, n_jobs=n_jobs)

        if model is None:
            return float("inf")

        x_fit = [x_train[index] for index in train_idx]
        y_fit = [y_train[index] for index in train_idx]
        x_test = [x_train[index] for index in test_idx]
        y_test = [y_train[index] for index in test_idx]

        model.fit(x_fit, y_fit)
        pred = model.predict(x_test)
        errors.append(float(mean_absolute_error(y_test, pred)))

    return sum(errors) / len(errors) if errors else float("inf")


def tune_legacy_engine_params(
    engine: str,
    train_rows: list[dict[str, Any]],
    target_return_column: str,
    *,
    n_iter: int = 15,
    cv: int = 3,
    n_jobs: int = 4,
) -> dict[str, Any]:
    x_train = [_feature_vector(row) for row in train_rows]
    y_train = _target_return_values(train_rows, target_return_column)

    if not x_train:
        return _engine_defaults(engine)

    best_params = _engine_defaults(engine)
    best_score = float("inf")

    for params in _candidate_param_sets(engine, n_iter=n_iter):
        score = _cv_mae(
            engine,
            x_train,
            y_train,
            params,
            cv=cv,
            n_jobs=n_jobs,
        )

        if score < best_score:
            best_score = score
            best_params = params

    return best_params


def fit_legacy_engine(
    engine: str,
    train_rows: list[dict[str, Any]],
    target_return_column: str,
    *,
    n_jobs: int = 4,
    autotune: bool = False,
    autotune_iter: int = 15,
    autotune_cv: int = 3,
) -> tuple[Any, dict[str, Any]]:
    x_train = [_feature_vector(row) for row in train_rows]
    y_train = _target_return_values(train_rows, target_return_column)

    if not x_train:
        return None, {"enabled": bool(autotune), "params": {}, "status": "NO_DATA"}

    params = (
        tune_legacy_engine_params(
            engine,
            train_rows,
            target_return_column,
            n_iter=autotune_iter,
            cv=autotune_cv,
            n_jobs=n_jobs,
        )
        if autotune
        else _engine_defaults(engine)
    )

    model = _make_model(engine, params, n_jobs=n_jobs)

    if model is None:
        return None, {
            "enabled": bool(autotune),
            "params": params,
            "status": "UNAVAILABLE",
        }

    try:
        model.fit(x_train, y_train)
    except Exception as exc:
        return None, {
            "enabled": bool(autotune),
            "params": params,
            "status": "FAILED",
            "error": str(exc),
        }

    return model, {
        "enabled": bool(autotune),
        "params": params,
        "status": "OK",
    }


def predict_legacy_engine(model: Any, row: dict[str, Any]) -> float:
    if model is None:
        return 0.0

    value = float(model.predict([_feature_vector(row)])[0])
    return _clip_return_value(value)


def majority_prediction(train_rows: list[dict[str, Any]], target_up_column: str) -> int:
    if not train_rows:
        return 0

    values = _target_up_values(train_rows, target_up_column)
    return 1 if sum(values) / len(values) >= 0.5 else 0


def momentum_rule_prediction(row: dict[str, Any]) -> int:
    return (
        1
        if _to_float(row.get("return_5d")) > 0
        and _to_float(row.get("trend_score"), 50.0) >= 45.0
        and _to_float(row.get("news_score"), 50.0) >= 45.0
        else 0
    )


def metric_report(
    *,
    rows: list[dict[str, Any]],
    predictions_up: list[int],
    predictions_return: list[float],
    target_up_column: str,
    target_return_column: str,
) -> dict[str, Any]:
    total = len(rows)

    if total == 0:
        return {
            "observations": 0,
            "accuracy": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "mae_return": 0.0,
            "target_up_rate": 0.0,
            "predicted_up_rate": 0.0,
            "mean_predicted_return": 0.0,
            "true_positive": 0,
            "true_negative": 0,
            "false_positive": 0,
            "false_negative": 0,
        }

    actual_up = _target_up_values(rows, target_up_column)
    actual_return = _target_return_values(rows, target_return_column)

    tp = sum(
        1
        for y, p in zip(actual_up, predictions_up, strict=True)
        if y == 1 and p == 1
    )
    tn = sum(
        1
        for y, p in zip(actual_up, predictions_up, strict=True)
        if y == 0 and p == 0
    )
    fp = sum(
        1
        for y, p in zip(actual_up, predictions_up, strict=True)
        if y == 0 and p == 1
    )
    fn = sum(
        1
        for y, p in zip(actual_up, predictions_up, strict=True)
        if y == 1 and p == 0
    )

    mae = sum(
        abs(y - p)
        for y, p in zip(actual_return, predictions_return, strict=True)
    ) / total

    precision_den = tp + fp
    recall_den = tp + fn

    return {
        "observations": total,
        "accuracy": round((tp + tn) / total, 4),
        "precision": round(tp / precision_den, 4) if precision_den else 0.0,
        "recall": round(tp / recall_den, 4) if recall_den else 0.0,
        "mae_return": round(mae, 4),
        "target_up_rate": round(sum(actual_up) / total, 4),
        "predicted_up_rate": round(sum(predictions_up) / total, 4),
        "mean_predicted_return": round(sum(predictions_return) / total, 4),
        "true_positive": tp,
        "true_negative": tn,
        "false_positive": fp,
        "false_negative": fn,
    }


def _normalize_base_engines(base_engines: list[str] | None = None) -> list[str]:
    if not base_engines:
        return LEGACY_BASE_ENGINES.copy()

    normalized: list[str] = []
    for engine in base_engines:
        name = str(engine).strip().lower()
        if name in LEGACY_BASE_ENGINES and name not in normalized:
            normalized.append(name)
    return normalized


def _zero_metrics() -> dict[str, Any]:
    return {
        "observations": 0,
        "accuracy": 0.0,
        "precision": 0.0,
        "recall": 0.0,
        "mae_return": 0.0,
        "target_up_rate": 0.0,
        "predicted_up_rate": 0.0,
        "mean_predicted_return": 0.0,
        "true_positive": 0,
        "true_negative": 0,
        "false_positive": 0,
        "false_negative": 0,
    }


def _temporal_train_test_split(
    rows: list[dict[str, Any]],
    *,
    min_train_rows: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(rows) <= min_train_rows:
        return rows, []

    split_index = max(min_train_rows, int(len(rows) * 0.70))
    split_index = min(split_index, len(rows) - 1)
    return rows[:split_index], rows[split_index:]


def _evaluate_ridge_ensemble_temporal(
    *,
    rows: list[dict[str, Any]],
    selected: list[str],
    dataset: str,
    horizon: int,
    min_train_rows: int,
    base_engines: list[str],
    n_jobs: int,
    autotune: bool,
    autotune_iter: int,
    autotune_cv: int,
) -> dict[str, Any]:
    target_return_column = f"target_return_{horizon}d"
    target_up_column = f"target_up_{horizon}d"
    train_rows, test_rows = _temporal_train_test_split(rows, min_train_rows=min_train_rows)

    engine_status: dict[str, str] = {}
    tuned_params: dict[str, dict[str, Any]] = {}
    base_models: dict[str, Any] = {}
    base_failure: dict[str, str] = {}

    for engine in base_engines:
        model, tune_meta = fit_legacy_engine(
            engine,
            train_rows,
            target_return_column,
            n_jobs=n_jobs,
            autotune=autotune,
            autotune_iter=autotune_iter,
            autotune_cv=autotune_cv,
        )
        base_models[engine] = model
        engine_status[engine] = "OK" if model is not None else tune_meta["status"]
        tuned_params[engine] = tune_meta
        if model is None:
            base_failure[engine] = str(
                tune_meta.get("error") or tune_meta.get("status") or "failed"
            )

    valid_base_engines = [engine for engine in base_engines if base_models.get(engine) is not None]
    failed_engines = [engine for engine in base_engines if engine not in valid_base_engines]

    pred_ret: dict[str, list[float]] = {engine: [] for engine in base_engines}
    pred_up: dict[str, list[int]] = {engine: [] for engine in base_engines}
    pred_ret["ridge_ensemble"] = []
    pred_up["ridge_ensemble"] = []
    ridge_coefficients: dict[str, Any] = {"intercept": 0.0, "weights": {}}
    reason = ""

    if len(valid_base_engines) >= 2 and test_rows:
        ridge_x: list[list[float]] = []
        ridge_y: list[float] = []
        for row in train_rows:
            base_pred = {
                engine: predict_legacy_engine(base_models[engine], row)
                for engine in valid_base_engines
            }
            guarded = apply_consensus_guard(base_pred)
            ridge_x.append([guarded.get(engine, 0.0) for engine in valid_base_engines])
            ridge_y.append(_to_float(row.get(target_return_column)))

        ridge = StableRidgeArbiter(alpha=1.0)
        ridge.fit(ridge_x, ridge_y)
        ridge_coefficients = {
            "intercept": round(ridge.intercept, 8),
            "weights": {
                engine: round(weight, 8)
                for engine, weight in zip(valid_base_engines, ridge.weights, strict=False)
            },
        }

        for row in test_rows:
            base_pred = {
                engine: predict_legacy_engine(base_models[engine], row)
                for engine in valid_base_engines
            }
            guarded = apply_consensus_guard(base_pred)
            for engine in base_engines:
                value = guarded.get(engine, 0.0)
                pred_ret[engine].append(value)
                pred_up[engine].append(1 if value > 0 else 0)

            ridge_value = ridge.predict_one(
                [guarded.get(engine, 0.0) for engine in valid_base_engines]
            )
            pred_ret["ridge_ensemble"].append(ridge_value)
            pred_up["ridge_ensemble"].append(1 if ridge_value > 0 else 0)

    if len(valid_base_engines) < 2:
        status = "FAIL"
        reason = "ridge_ensemble requires at least 2 base engines"
    elif failed_engines:
        status = "DEGRADED"
    else:
        status = "OK"

    engine_status["ridge_ensemble"] = status
    tuned_params["ridge_ensemble"] = {
        "enabled": False,
        "params": {"alpha": 1.0},
        "base_engines": valid_base_engines,
        "failed_engines": {
            engine: base_failure.get(engine, "failed") for engine in failed_engines
        },
        "status": status,
    }

    base_metrics = {
        engine: (
            metric_report(
                rows=test_rows,
                predictions_up=pred_up[engine],
                predictions_return=pred_ret[engine],
                target_up_column=target_up_column,
                target_return_column=target_return_column,
            )
            if engine in valid_base_engines
            and test_rows
            and len(pred_up[engine]) == len(test_rows)
            else _zero_metrics()
        )
        for engine in base_engines
    }
    ensemble_metrics = (
        metric_report(
            rows=test_rows,
            predictions_up=pred_up["ridge_ensemble"],
            predictions_return=pred_ret["ridge_ensemble"],
            target_up_column=target_up_column,
            target_return_column=target_return_column,
        )
        if len(valid_base_engines) >= 2 and test_rows
        else _zero_metrics()
    )
    models = {**base_metrics, "ridge_ensemble": ensemble_metrics}
    trained_models = [
        *valid_base_engines,
        *(["ridge_ensemble"] if status in {"OK", "DEGRADED"} else []),
    ]

    return {
        "status": status,
        "reason": reason,
        "dataset": dataset,
        "horizon": horizon,
        "min_train_rows": min_train_rows,
        "n_jobs": n_jobs,
        "autotune": {
            "enabled": bool(autotune),
            "n_iter": int(autotune_iter),
            "cv": int(autotune_cv),
            "scoring": "neg_mean_absolute_error",
            "tuned_params": tuned_params,
        },
        "engines": selected,
        "engine_status": engine_status,
        "engine_used": "ridge_ensemble",
        "is_baseline": False,
        "trained_models": trained_models,
        "base_engines": base_engines,
        "valid_base_engines": valid_base_engines,
        "failed_engines": failed_engines,
        "meta_model": "ridge",
        "base_metrics": base_metrics,
        "ensemble_metrics": ensemble_metrics,
        "ridge_coefficients": ridge_coefficients,
        "rows": len(rows),
        "evaluated_rows": len(test_rows),
        "models": models,
    }


def evaluate_legacy_walk_forward(
    *,
    rows: list[dict[str, Any]],
    dataset: str,
    horizon: int = 5,
    min_train_rows: int = 100,
    engines: list[str] | None = None,
    base_engines: list[str] | None = None,
    n_jobs: int = 4,
    autotune: bool = False,
    autotune_iter: int = 15,
    autotune_cv: int = 3,
) -> dict[str, Any]:
    selected = parse_legacy_engines(engines)
    uses_ridge_ensemble = "ridge_ensemble" in selected
    base_engine_list = _normalize_base_engines(base_engines)
    rows = sorted(
        rows,
        key=lambda row: (str(row.get("date", "")), str(row.get("ticker", ""))),
    )

    if uses_ridge_ensemble:
        return _evaluate_ridge_ensemble_temporal(
            rows=rows,
            selected=selected,
            dataset=dataset,
            horizon=horizon,
            min_train_rows=min_train_rows,
            base_engines=base_engine_list,
            n_jobs=n_jobs,
            autotune=autotune,
            autotune_iter=autotune_iter,
            autotune_cv=autotune_cv,
        )

    target_return_column = f"target_return_{horizon}d"
    target_up_column = f"target_up_{horizon}d"

    evaluation_rows: list[dict[str, Any]] = []
    tracked_engines = list(
        dict.fromkeys(
            [
                *selected,
                *(LEGACY_BASE_ENGINES if uses_ridge_ensemble else []),
            ]
        )
    )
    pred_up: dict[str, list[int]] = {engine: [] for engine in tracked_engines}
    pred_ret: dict[str, list[float]] = {engine: [] for engine in tracked_engines}
    engine_status: dict[str, str] = {}
    tuned_params: dict[str, dict[str, Any]] = {}
    base_success: set[str] = set()
    base_failure: dict[str, str] = {}
    final_ridge_coefficients: dict[str, Any] = {"intercept": 0.0, "weights": {}}
    ensemble_reason = ""

    for engine in selected:
        if engine in BASELINE_ENGINES:
            engine_status[engine] = "BASELINE"

    dates = sorted({str(row.get("date", "")) for row in rows if row.get("date")})

    for current_date in dates:
        train_rows = [row for row in rows if str(row.get("date", "")) < current_date]
        test_rows = [row for row in rows if str(row.get("date", "")) == current_date]

        if len(train_rows) < min_train_rows:
            continue

        base_needed = [
            engine
            for engine in LEGACY_BASE_ENGINES
            if engine in selected or uses_ridge_ensemble
        ]

        base_models: dict[str, Any] = {}

        for engine in base_needed:
            model, tune_meta = fit_legacy_engine(
                engine,
                train_rows,
                target_return_column,
                n_jobs=n_jobs,
                autotune=autotune,
                autotune_iter=autotune_iter,
                autotune_cv=autotune_cv,
            )
            base_models[engine] = model
            engine_status[engine] = "OK" if model is not None else tune_meta["status"]
            tuned_params[engine] = tune_meta
            if model is not None:
                base_success.add(engine)
            else:
                base_failure[engine] = str(
                    tune_meta.get("error") or tune_meta.get("status") or "failed"
                )

        ridge = StableRidgeArbiter(alpha=1.0)
        ridge_base_engines = [
            engine for engine in LEGACY_BASE_ENGINES if base_models.get(engine) is not None
        ]

        if uses_ridge_ensemble and len(ridge_base_engines) >= 2:
            ridge_x: list[list[float]] = []
            ridge_y: list[float] = []

            for train_row in train_rows:
                base_pred = {
                    engine: predict_legacy_engine(base_models[engine], train_row)
                    for engine in ridge_base_engines
                }
                guarded = apply_consensus_guard(base_pred)

                if guarded:
                    ridge_x.append(
                        [guarded.get(engine, 0.0) for engine in ridge_base_engines]
                    )
                    ridge_y.append(_to_float(train_row.get(target_return_column)))

            ridge.fit(ridge_x, ridge_y)
            final_ridge_coefficients = {
                "intercept": round(ridge.intercept, 8),
                "weights": {
                    engine: round(weight, 8)
                    for engine, weight in zip(
                        ridge_base_engines,
                        ridge.weights,
                        strict=False,
                    )
                },
            }
            tuned_params["ridge_ensemble"] = {
                "enabled": False,
                "params": {"alpha": 1.0},
                "base_engines": ridge_base_engines,
                "status": "OK",
            }
        elif uses_ridge_ensemble:
            ensemble_reason = "ridge_ensemble requires at least 2 base engines"
            tuned_params["ridge_ensemble"] = {
                "enabled": False,
                "params": {"alpha": 1.0},
                "base_engines": ridge_base_engines,
                "status": "FAIL",
            }

        majority = majority_prediction(train_rows, target_up_column)

        for row in test_rows:
            evaluation_rows.append(row)

            if "rolling_majority" in selected:
                pred_up["rolling_majority"].append(majority)
                pred_ret["rolling_majority"].append(0.0)

            base_pred = {
                engine: predict_legacy_engine(model, row)
                for engine, model in base_models.items()
                if model is not None
            }
            guarded = apply_consensus_guard(base_pred)

            for engine in LEGACY_BASE_ENGINES:
                if engine in tracked_engines:
                    value = guarded.get(engine, 0.0)
                    pred_ret[engine].append(value)
                    pred_up[engine].append(1 if value > 0 else 0)

            if uses_ridge_ensemble:
                ridge_input = [guarded.get(engine, 0.0) for engine in ridge_base_engines]
                value = ridge.predict_one(ridge_input)
                pred_ret["ridge_ensemble"].append(value)
                pred_up["ridge_ensemble"].append(1 if value > 0 else 0)

    valid_base_engines = [engine for engine in LEGACY_BASE_ENGINES if engine in base_success]
    failed_engines = [
        engine
        for engine in LEGACY_BASE_ENGINES
        if uses_ridge_ensemble and engine not in valid_base_engines
    ]

    if uses_ridge_ensemble:
        if len(valid_base_engines) < 2:
            engine_status["ridge_ensemble"] = "FAIL"
            ensemble_reason = ensemble_reason or "ridge_ensemble requires at least 2 base engines"
        elif failed_engines:
            engine_status["ridge_ensemble"] = "DEGRADED"
        else:
            engine_status["ridge_ensemble"] = "OK"

        tuned_params.setdefault(
            "ridge_ensemble",
            {
                "enabled": False,
                "params": {"alpha": 1.0},
                "base_engines": valid_base_engines,
                "status": engine_status["ridge_ensemble"],
            },
        )
        tuned_params["ridge_ensemble"]["status"] = engine_status["ridge_ensemble"]
        tuned_params["ridge_ensemble"]["failed_engines"] = {
            engine: base_failure.get(engine, "failed") for engine in failed_engines
        }

    models = {
        engine: metric_report(
            rows=evaluation_rows,
            predictions_up=pred_up[engine],
            predictions_return=pred_ret[engine],
            target_up_column=target_up_column,
            target_return_column=target_return_column,
        )
        for engine in tracked_engines
    }
    trained_models = [
        engine
        for engine in tracked_engines
        if (
            engine in LEGACY_BASE_ENGINES
            and engine_status.get(engine) == "OK"
        )
        or (
            engine == "ridge_ensemble"
            and engine_status.get(engine) in {"OK", "DEGRADED"}
        )
    ]
    baseline_models = [engine for engine in selected if engine in BASELINE_ENGINES]
    engine_used = (
        "ridge_ensemble"
        if uses_ridge_ensemble
        else (trained_models[0]
        if trained_models
        else (baseline_models[0] if baseline_models else "-")
        )
    )
    status = engine_status.get("ridge_ensemble", "OK") if uses_ridge_ensemble else "OK"
    if selected == ["rolling_majority"]:
        status = "BASELINE"

    base_metrics = {
        engine: models.get(engine, {})
        for engine in LEGACY_BASE_ENGINES
        if engine in models
    }
    ensemble_metrics = models.get("ridge_ensemble", {})

    return {
        "status": status,
        "reason": ensemble_reason,
        "dataset": dataset,
        "horizon": horizon,
        "min_train_rows": min_train_rows,
        "n_jobs": n_jobs,
        "autotune": {
            "enabled": bool(autotune),
            "n_iter": int(autotune_iter),
            "cv": int(autotune_cv),
            "scoring": "neg_mean_absolute_error",
            "tuned_params": tuned_params,
        },
        "engines": selected,
        "engine_status": engine_status,
        "engine_used": engine_used,
        "is_baseline": engine_used in BASELINE_ENGINES,
        "trained_models": trained_models,
        "base_engines": LEGACY_BASE_ENGINES.copy() if uses_ridge_ensemble else [],
        "valid_base_engines": valid_base_engines if uses_ridge_ensemble else [],
        "failed_engines": failed_engines if uses_ridge_ensemble else [],
        "meta_model": "ridge" if uses_ridge_ensemble else "",
        "base_metrics": base_metrics,
        "ensemble_metrics": ensemble_metrics,
        "ridge_coefficients": final_ridge_coefficients if uses_ridge_ensemble else {},
        "rows": len(rows),
        "evaluated_rows": len(evaluation_rows),
        "models": models,
    }
