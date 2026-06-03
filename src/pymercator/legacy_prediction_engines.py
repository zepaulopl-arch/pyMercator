
from __future__ import annotations

import itertools
import math
import random
from typing import Any

try:
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.ensemble import (
        ExtraTreesClassifier,
        ExtraTreesRegressor,
        GradientBoostingClassifier,
        GradientBoostingRegressor,
        RandomForestClassifier,
        RandomForestRegressor,
    )
    from sklearn.metrics import mean_absolute_error
    from sklearn.model_selection import TimeSeriesSplit

    SKLEARN_AVAILABLE = True
except Exception:
    CalibratedClassifierCV = None
    ExtraTreesClassifier = None
    ExtraTreesRegressor = None
    GradientBoostingClassifier = None
    GradientBoostingRegressor = None
    RandomForestClassifier = None
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
DEGENERATE_UP_RATE_LOW: float = 0.20
DEGENERATE_UP_RATE_HIGH: float = 0.80
DEFAULT_PROBABILITY_CALIBRATION: dict[str, Any] = {
    "enabled": True,
    "method": "sigmoid",
    "cv": 3,
    "threshold_metric": "balanced_accuracy",
}

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


def _feature_matrix(rows: list[dict[str, Any]]) -> list[list[float]]:
    return [_feature_vector(row) for row in rows]


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


def _clip_probability(value: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.5
    if math.isnan(number):
        return 0.5
    return max(0.0, min(1.0, number))


def _return_to_probability(value: float) -> float:
    clipped = _clip_return_value(value)
    if clipped <= -50:
        return 0.0
    if clipped >= 50:
        return 1.0
    return _clip_probability(1.0 / (1.0 + math.exp(-clipped)))


def _normalize_calibration_config(calibration: dict[str, Any] | None = None) -> dict[str, Any]:
    config = DEFAULT_PROBABILITY_CALIBRATION.copy()
    if isinstance(calibration, dict):
        config.update(calibration)

    method = str(config.get("method", "sigmoid")).strip().lower()
    if method in {"platt", "platt_scaling"}:
        method = "sigmoid"
    if method not in {"sigmoid", "isotonic"}:
        method = "sigmoid"

    metric = str(config.get("threshold_metric", "balanced_accuracy")).strip().lower()
    if metric not in {"balanced_accuracy", "accuracy", "f1", "youden"}:
        metric = "balanced_accuracy"

    return {
        "enabled": bool(config.get("enabled", True)),
        "method": method,
        "cv": max(2, int(config.get("cv", 3) or 3)),
        "threshold_metric": metric,
    }


def _confusion_counts(actual: list[int], predictions: list[int]) -> dict[str, int]:
    true_positive = sum(
        1 for y, p in zip(actual, predictions, strict=True) if y == 1 and p == 1
    )
    true_negative = sum(
        1 for y, p in zip(actual, predictions, strict=True) if y == 0 and p == 0
    )
    false_positive = sum(
        1 for y, p in zip(actual, predictions, strict=True) if y == 0 and p == 1
    )
    false_negative = sum(
        1 for y, p in zip(actual, predictions, strict=True) if y == 1 and p == 0
    )
    return {
        "true_positive": true_positive,
        "true_negative": true_negative,
        "false_positive": false_positive,
        "false_negative": false_negative,
    }


def _rate(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 6) if denominator else 0.0


def _is_degenerate_up_rate(value: float) -> bool:
    return value > DEGENERATE_UP_RATE_HIGH or value < DEGENERATE_UP_RATE_LOW


def _quality_status_from_up_rate(value: float) -> str:
    return "DEGENERATE" if _is_degenerate_up_rate(value) else "OK"


def _probability_threshold_candidates(probabilities: list[float]) -> list[float]:
    values = sorted({_clip_probability(value) for value in probabilities})
    if not values:
        return [0.5]

    candidates = {0.5, 0.0, 1.0, *values}
    for left, right in zip(values, values[1:], strict=False):
        candidates.add((left + right) / 2.0)

    return sorted(candidates)


def tune_probability_threshold(
    probabilities: list[float],
    actual_up: list[int],
    *,
    metric: str = "balanced_accuracy",
) -> dict[str, Any]:
    if not probabilities or len(probabilities) != len(actual_up):
        return {
            "threshold": 0.5,
            "metric": metric,
            "score": 0.0,
            "predicted_up_rate": 0.0,
            "target_up_rate": 0.0,
            "status": "NO_DATA",
        }

    normalized_metric = str(metric or "balanced_accuracy").strip().lower()
    if normalized_metric not in {"balanced_accuracy", "accuracy", "f1", "youden"}:
        normalized_metric = "balanced_accuracy"

    normalized_actual = [1 if int(value) else 0 for value in actual_up]
    clipped_probabilities = [_clip_probability(value) for value in probabilities]
    total = len(clipped_probabilities)
    total_positive = sum(normalized_actual)
    total_negative = total - total_positive
    target_up_rate = total_positive / total
    ordered_pairs = sorted(
        zip(clipped_probabilities, normalized_actual, strict=True),
        key=lambda item: item[0],
    )
    best: tuple[float, float, float, float, float, float, int, dict[str, Any]] | None = None
    tp = total_positive
    fp = total_negative
    cursor = 0

    for candidate_index, threshold in enumerate(
        _probability_threshold_candidates(clipped_probabilities)
    ):
        while cursor < total and ordered_pairs[cursor][0] < threshold:
            _probability, actual = ordered_pairs[cursor]
            if actual:
                tp -= 1
            else:
                fp -= 1
            cursor += 1

        fn = total_positive - tp
        tn = total_negative - fp
        predicted_positive = tp + fp
        predicted_up_rate = predicted_positive / total
        recall = _rate(tp, tp + fn)
        specificity = _rate(tn, tn + fp)
        precision = _rate(tp, tp + fp)
        false_positive_rate = _rate(fp, fp + tn)
        accuracy = _rate(tp + tn, total)

        if normalized_metric == "accuracy":
            score = accuracy
        elif normalized_metric == "f1":
            score = _rate(2 * precision * recall, precision + recall)
        elif normalized_metric == "youden":
            score = round(recall - false_positive_rate, 6)
        else:
            score = round((recall + specificity) / 2.0, 6)

        is_degenerate = _is_degenerate_up_rate(predicted_up_rate)
        ranked = (
            0.0 if is_degenerate else 1.0,
            -abs(predicted_up_rate - target_up_rate),
            score,
            -false_positive_rate,
            -abs(threshold - 0.5),
            threshold,
            -candidate_index,
            {
                "threshold": round(threshold, 6),
                "metric": normalized_metric,
                "score": round(score, 6),
                "predicted_up_rate": round(predicted_up_rate, 6),
                "target_up_rate": round(target_up_rate, 6),
                "false_positive_rate": false_positive_rate,
                "quality_status": "DEGENERATE" if is_degenerate else "OK",
                "status": "OK",
            },
        )
        if best is None or ranked > best:
            best = ranked

    return dict(best[-1]) if best else {
        "threshold": 0.5,
        "metric": normalized_metric,
        "score": 0.0,
        "predicted_up_rate": round(target_up_rate, 6),
        "target_up_rate": round(target_up_rate, 6),
        "status": "NO_CANDIDATES",
    }


def _quantile(ordered_values: list[float], fraction: float) -> float:
    if not ordered_values:
        return 0.0
    if len(ordered_values) == 1:
        return ordered_values[0]

    position = (len(ordered_values) - 1) * fraction
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered_values[lower]
    weight = position - lower
    return ordered_values[lower] * (1.0 - weight) + ordered_values[upper] * weight


def probability_stats(probabilities: list[float]) -> dict[str, Any]:
    values = [_clip_probability(value) for value in probabilities]
    count = len(values)
    if count == 0:
        return {
            "count": 0,
            "min": 0.0,
            "max": 0.0,
            "mean": 0.0,
            "std": 0.0,
            "p05": 0.0,
            "p25": 0.0,
            "p50": 0.0,
            "p75": 0.0,
            "p95": 0.0,
        }

    ordered = sorted(values)
    mean = sum(values) / count
    variance = sum((value - mean) ** 2 for value in values) / count
    return {
        "count": count,
        "min": round(ordered[0], 6),
        "max": round(ordered[-1], 6),
        "mean": round(mean, 6),
        "std": round(math.sqrt(variance), 6),
        "p05": round(_quantile(ordered, 0.05), 6),
        "p25": round(_quantile(ordered, 0.25), 6),
        "p50": round(_quantile(ordered, 0.50), 6),
        "p75": round(_quantile(ordered, 0.75), 6),
        "p95": round(_quantile(ordered, 0.95), 6),
    }


def probability_distribution(probabilities: list[float]) -> dict[str, int]:
    buckets = {f"{index / 10:.1f}-{(index + 1) / 10:.1f}": 0 for index in range(10)}
    for value in probabilities:
        clipped = _clip_probability(value)
        index = min(9, int(clipped * 10))
        key = f"{index / 10:.1f}-{(index + 1) / 10:.1f}"
        buckets[key] += 1
    return buckets


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


def _make_classifier(
    engine: str,
    params: dict[str, Any],
    *,
    n_jobs: int = 4,
) -> Any:
    if engine == "extratrees":
        if not SKLEARN_AVAILABLE or ExtraTreesClassifier is None:
            return None

        return ExtraTreesClassifier(
            **params,
            random_state=42,
            n_jobs=n_jobs,
        )

    if engine == "randomforest":
        if not SKLEARN_AVAILABLE or RandomForestClassifier is None:
            return None

        return RandomForestClassifier(
            **params,
            random_state=42,
            n_jobs=n_jobs,
        )

    if engine == "gradientboosting":
        if not SKLEARN_AVAILABLE or GradientBoostingClassifier is None:
            return None

        return GradientBoostingClassifier(
            **params,
            random_state=42,
        )

    return None


def _make_calibrated_classifier(
    classifier: Any,
    *,
    method: str,
    cv: int,
) -> Any:
    if CalibratedClassifierCV is None:
        return None

    try:
        return CalibratedClassifierCV(
            estimator=classifier,
            method=method,
            cv=cv,
        )
    except TypeError:
        return CalibratedClassifierCV(
            base_estimator=classifier,
            method=method,
            cv=cv,
        )


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


def fit_calibrated_legacy_classifier(
    engine: str,
    train_rows: list[dict[str, Any]],
    target_up_column: str,
    *,
    params: dict[str, Any],
    calibration: dict[str, Any] | None = None,
    n_jobs: int = 4,
) -> tuple[Any, dict[str, Any]]:
    config = _normalize_calibration_config(calibration)
    x_train = _feature_matrix(train_rows)
    y_train = _target_up_values(train_rows, target_up_column)
    meta: dict[str, Any] = {
        "enabled": config["enabled"],
        "method": config["method"],
        "cv": config["cv"],
        "threshold_metric": config["threshold_metric"],
        "params": params,
        "status": "OK",
        "probability_source": "calibrated_classifier",
    }

    if not x_train:
        meta["status"] = "NO_DATA"
        return None, meta

    class_counts = {0: y_train.count(0), 1: y_train.count(1)}
    meta["class_counts"] = class_counts
    min_class_count = min(class_counts.values())
    if min_class_count < 2:
        meta["status"] = "ONE_CLASS"
        meta["probability_source"] = "return_sigmoid_fallback"
        return None, meta

    classifier = _make_classifier(engine, params, n_jobs=n_jobs)
    if classifier is None:
        meta["status"] = "UNAVAILABLE"
        meta["probability_source"] = "return_sigmoid_fallback"
        return None, meta

    try:
        if not config["enabled"]:
            classifier.fit(x_train, y_train)
            meta["status"] = "RAW_PROBABILITY"
            meta["probability_source"] = "raw_classifier"
            return classifier, meta

        folds = min(config["cv"], min_class_count)
        calibrated = _make_calibrated_classifier(
            classifier,
            method=config["method"],
            cv=folds,
        )
        if calibrated is None:
            meta["status"] = "UNAVAILABLE"
            meta["probability_source"] = "return_sigmoid_fallback"
            return None, meta

        calibrated.fit(x_train, y_train)
        meta["cv"] = folds
        return calibrated, meta
    except Exception as exc:
        meta["status"] = "FAILED"
        meta["error"] = str(exc)
        meta["probability_source"] = "return_sigmoid_fallback"
        return None, meta


def predict_legacy_engine(model: Any, row: dict[str, Any]) -> float:
    if model is None:
        return 0.0

    value = float(model.predict([_feature_vector(row)])[0])
    return _clip_return_value(value)


def predict_legacy_engine_many(
    model: Any,
    rows: list[dict[str, Any]],
) -> list[float]:
    if model is None or not rows:
        return [0.0 for _ in rows]

    values = model.predict(_feature_matrix(rows))
    return [_clip_return_value(float(value)) for value in values]


def predict_legacy_engine_probability(model: Any, row: dict[str, Any]) -> float | None:
    if model is None or not hasattr(model, "predict_proba"):
        return None

    probabilities = model.predict_proba([_feature_vector(row)])
    if probabilities is None:
        return None
    first = probabilities[0]
    classes = list(getattr(model, "classes_", []))
    if 1 in classes:
        return _clip_probability(float(first[classes.index(1)]))
    if len(first) >= 2:
        return _clip_probability(float(first[1]))
    return _clip_probability(float(first[0]))


def predict_legacy_engine_probability_many(
    model: Any,
    rows: list[dict[str, Any]],
) -> list[float] | None:
    if model is None or not rows or not hasattr(model, "predict_proba"):
        return None

    probabilities = model.predict_proba(_feature_matrix(rows))
    classes = list(getattr(model, "classes_", []))
    index = classes.index(1) if 1 in classes else 1
    values: list[float] = []
    for row_probabilities in probabilities:
        selected_index = index if len(row_probabilities) > index else 0
        values.append(_clip_probability(float(row_probabilities[selected_index])))
    return values


def _probabilities_for_rows(
    *,
    probability_model: Any,
    rows: list[dict[str, Any]],
    fallback_returns: list[float],
) -> list[float]:
    probabilities = predict_legacy_engine_probability_many(probability_model, rows)
    if probabilities is not None and len(probabilities) == len(rows):
        return probabilities
    return [_return_to_probability(value) for value in fallback_returns]


def _threshold_predictions(probabilities: list[float], threshold: float) -> list[int]:
    return [1 if _clip_probability(value) >= threshold else 0 for value in probabilities]


def _normalized_abs_weights(engines: list[str], weights: list[float]) -> dict[str, float]:
    raw = {
        engine: abs(float(weight))
        for engine, weight in zip(engines, weights, strict=False)
    }
    total = sum(raw.values())
    if total <= 0:
        return {engine: 1.0 / max(1, len(engines)) for engine in engines}
    return {engine: value / total for engine, value in raw.items()}


def _weighted_probabilities(
    probabilities_by_engine: dict[str, list[float]],
    engines: list[str],
    weights: dict[str, float],
) -> list[float]:
    if not engines:
        return []

    row_count = min(
        (len(probabilities_by_engine.get(engine, [])) for engine in engines),
        default=0,
    )
    if row_count <= 0:
        return []

    total_weight = sum(weights.get(engine, 0.0) for engine in engines) or float(len(engines))
    values: list[float] = []
    for index in range(row_count):
        weighted = 0.0
        for engine in engines:
            weight = weights.get(engine, 0.0) or 1.0
            weighted += weight * _clip_probability(probabilities_by_engine[engine][index])
        values.append(_clip_probability(weighted / total_weight))
    return values


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
    probabilities_up: list[float] | None = None,
    optimal_threshold: float | None = None,
    threshold_tuning: dict[str, Any] | None = None,
    calibration: dict[str, Any] | None = None,
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
            "false_positive_rate": 0.0,
            "false_negative_rate": 0.0,
            "TP": 0,
            "TN": 0,
            "FP": 0,
            "FN": 0,
            "confusion_matrix": {"TP": 0, "TN": 0, "FP": 0, "FN": 0},
            "quality_status": "NO_DATA",
        }

    actual_up = _target_up_values(rows, target_up_column)
    actual_return = _target_return_values(rows, target_return_column)

    counts = _confusion_counts(actual_up, predictions_up)
    tp = counts["true_positive"]
    tn = counts["true_negative"]
    fp = counts["false_positive"]
    fn = counts["false_negative"]

    mae = sum(
        abs(y - p)
        for y, p in zip(actual_return, predictions_return, strict=True)
    ) / total

    precision_den = tp + fp
    recall_den = tp + fn
    predicted_up_rate = sum(predictions_up) / total
    quality_status = _quality_status_from_up_rate(predicted_up_rate)

    report: dict[str, Any] = {
        "observations": total,
        "accuracy": round((tp + tn) / total, 4),
        "precision": round(tp / precision_den, 4) if precision_den else 0.0,
        "recall": round(tp / recall_den, 4) if recall_den else 0.0,
        "mae_return": round(mae, 4),
        "target_up_rate": round(sum(actual_up) / total, 4),
        "predicted_up_rate": round(predicted_up_rate, 4),
        "mean_predicted_return": round(sum(predictions_return) / total, 4),
        "true_positive": tp,
        "true_negative": tn,
        "false_positive": fp,
        "false_negative": fn,
        "false_positive_rate": _rate(fp, fp + tn),
        "false_negative_rate": _rate(fn, fn + tp),
        "TP": tp,
        "TN": tn,
        "FP": fp,
        "FN": fn,
        "confusion_matrix": {
            "TP": tp,
            "TN": tn,
            "FP": fp,
            "FN": fn,
        },
        "quality_status": quality_status,
    }

    if quality_status == "DEGENERATE":
        report["degenerate_warning"] = (
            "DEGENERATE WARNING: predicted_up_rate outside 0.20-0.80"
        )

    if optimal_threshold is not None:
        report["optimal_threshold"] = round(float(optimal_threshold), 6)
    if threshold_tuning:
        report["threshold_tuning"] = dict(threshold_tuning)
    if probabilities_up is not None:
        report["calibrated_probability_stats"] = probability_stats(probabilities_up)
        report["probability_distribution"] = probability_distribution(probabilities_up)
    if calibration:
        report["calibration"] = dict(calibration)

    return report


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
        "false_positive_rate": 0.0,
        "false_negative_rate": 0.0,
        "TP": 0,
        "TN": 0,
        "FP": 0,
        "FN": 0,
        "confusion_matrix": {"TP": 0, "TN": 0, "FP": 0, "FN": 0},
        "quality_status": "NO_DATA",
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
    calibration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target_return_column = f"target_return_{horizon}d"
    target_up_column = f"target_up_{horizon}d"
    train_rows, test_rows = _temporal_train_test_split(rows, min_train_rows=min_train_rows)
    calibration_config = _normalize_calibration_config(calibration)

    engine_status: dict[str, str] = {}
    tuned_params: dict[str, dict[str, Any]] = {}
    base_models: dict[str, Any] = {}
    probability_models: dict[str, Any] = {}
    calibration_meta: dict[str, dict[str, Any]] = {}
    threshold_tuning: dict[str, dict[str, Any]] = {}
    probability_thresholds: dict[str, float] = {}
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
            calibration_meta[engine] = {
                **calibration_config,
                "status": "SKIPPED",
                "probability_source": "return_sigmoid_fallback",
            }
            continue

        probability_model, probability_meta = fit_calibrated_legacy_classifier(
            engine,
            train_rows,
            target_up_column,
            params=dict(tune_meta.get("params", {})),
            calibration=calibration_config,
            n_jobs=n_jobs,
        )
        probability_models[engine] = probability_model
        calibration_meta[engine] = probability_meta

    valid_base_engines = [engine for engine in base_engines if base_models.get(engine) is not None]
    failed_engines = [engine for engine in base_engines if engine not in valid_base_engines]

    pred_ret: dict[str, list[float]] = {engine: [] for engine in base_engines}
    pred_up: dict[str, list[int]] = {engine: [] for engine in base_engines}
    pred_prob: dict[str, list[float]] = {engine: [] for engine in base_engines}
    pred_ret["ridge_ensemble"] = []
    pred_up["ridge_ensemble"] = []
    pred_prob["ridge_ensemble"] = []
    ridge_coefficients: dict[str, Any] = {"intercept": 0.0, "weights": {}}
    ridge_probability_weights: dict[str, float] = {}
    reason = ""

    if len(valid_base_engines) >= 2 and test_rows:
        train_predictions = {
            engine: predict_legacy_engine_many(base_models[engine], train_rows)
            for engine in valid_base_engines
        }
        train_probabilities = {
            engine: _probabilities_for_rows(
                probability_model=probability_models.get(engine),
                rows=train_rows,
                fallback_returns=train_predictions[engine],
            )
            for engine in valid_base_engines
        }
        actual_train_up = _target_up_values(train_rows, target_up_column)
        for engine in valid_base_engines:
            tuning = tune_probability_threshold(
                train_probabilities[engine],
                actual_train_up,
                metric=calibration_config["threshold_metric"],
            )
            threshold_tuning[engine] = tuning
            probability_thresholds[engine] = float(tuning.get("threshold", 0.5))

        ridge_x: list[list[float]] = []
        ridge_y: list[float] = []
        for row_index, row in enumerate(train_rows):
            base_pred = {
                engine: train_predictions[engine][row_index]
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
        ridge_probability_weights = _normalized_abs_weights(valid_base_engines, ridge.weights)

        train_ensemble_probabilities = _weighted_probabilities(
            train_probabilities,
            valid_base_engines,
            ridge_probability_weights,
        )
        ensemble_tuning = tune_probability_threshold(
            train_ensemble_probabilities,
            actual_train_up[: len(train_ensemble_probabilities)],
            metric=calibration_config["threshold_metric"],
        )
        threshold_tuning["ridge_ensemble"] = ensemble_tuning
        probability_thresholds["ridge_ensemble"] = float(ensemble_tuning.get("threshold", 0.5))

        test_predictions = {
            engine: predict_legacy_engine_many(base_models[engine], test_rows)
            for engine in valid_base_engines
        }
        test_probabilities = {
            engine: _probabilities_for_rows(
                probability_model=probability_models.get(engine),
                rows=test_rows,
                fallback_returns=test_predictions[engine],
            )
            for engine in valid_base_engines
        }
        test_ensemble_probabilities = _weighted_probabilities(
            test_probabilities,
            valid_base_engines,
            ridge_probability_weights,
        )
        for row_index, _row in enumerate(test_rows):
            base_pred = {
                engine: test_predictions[engine][row_index]
                for engine in valid_base_engines
            }
            guarded = apply_consensus_guard(base_pred)
            for engine in base_engines:
                value = guarded.get(engine, 0.0)
                pred_ret[engine].append(value)
                probability = (
                    test_probabilities.get(engine, [])[row_index]
                    if engine in test_probabilities
                    else _return_to_probability(value)
                )
                pred_prob[engine].append(probability)
                threshold = probability_thresholds.get(engine, 0.5)
                pred_up[engine].append(1 if probability >= threshold else 0)

            ridge_value = ridge.predict_one(
                [guarded.get(engine, 0.0) for engine in valid_base_engines]
            )
            pred_ret["ridge_ensemble"].append(ridge_value)
            ridge_probability = (
                test_ensemble_probabilities[row_index]
                if row_index < len(test_ensemble_probabilities)
                else _return_to_probability(ridge_value)
            )
            pred_prob["ridge_ensemble"].append(ridge_probability)
            pred_up["ridge_ensemble"].append(
                1 if ridge_probability >= probability_thresholds.get("ridge_ensemble", 0.5) else 0
            )

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
        "probability_weights": {
            engine: round(weight, 6)
            for engine, weight in ridge_probability_weights.items()
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
                probabilities_up=pred_prob[engine],
                optimal_threshold=probability_thresholds.get(engine),
                threshold_tuning=threshold_tuning.get(engine),
                calibration=calibration_meta.get(engine),
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
            probabilities_up=pred_prob["ridge_ensemble"],
            optimal_threshold=probability_thresholds.get("ridge_ensemble"),
            threshold_tuning=threshold_tuning.get("ridge_ensemble"),
            calibration={
                **calibration_config,
                "status": "OK",
                "probability_source": "weighted_base_probabilities",
                "weights": {
                    engine: round(weight, 6)
                    for engine, weight in ridge_probability_weights.items()
                },
            },
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
        "calibration": {
            **calibration_config,
            "models": calibration_meta,
            "thresholds": {
                engine: round(value, 6)
                for engine, value in probability_thresholds.items()
            },
            "threshold_tuning": threshold_tuning,
        },
        "probability_thresholds": {
            engine: round(value, 6)
            for engine, value in probability_thresholds.items()
        },
        "optimal_threshold": round(
            probability_thresholds.get("ridge_ensemble", 0.5),
            6,
        ),
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
    calibration: dict[str, Any] | None = None,
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
            calibration=calibration,
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
