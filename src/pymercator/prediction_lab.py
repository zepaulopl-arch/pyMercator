from __future__ import annotations

import csv
import json
import math
import random
from pathlib import Path
from typing import Any

from pymercator.legacy_prediction_engines import (
    available_legacy_engines,
    evaluate_legacy_walk_forward,
)

DATASET_COLUMNS = [
    "date",
    "ticker",
    "sector",
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


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def _read_csv(path: str | Path) -> list[dict[str, Any]]:
    file_path = Path(path)

    with file_path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _price_file_for_ticker(prices_dir: str | Path, ticker: str) -> Path:
    root = Path(prices_dir)
    ticker_text = ticker.upper().strip()
    ticker_base = ticker_text.replace(".SA", "")

    candidates = [
        root / f"{ticker_text}.csv",
        root / f"{ticker_base}.SA.csv",
        root / f"{ticker_base}.csv",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[1]


def _read_price_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            date_value = str(row.get("date", "")).strip()
            close = _to_float(row.get("close"), 0.0)

            if date_value and close > 0:
                rows.append(
                    {
                        "date": date_value,
                        "close": close,
                    }
                )

    rows.sort(key=lambda item: str(item["date"]))
    return rows


def _return_pct(closes: list[float], index: int, window: int) -> float:
    if index - window < 0:
        return 0.0

    current = closes[index]
    previous = closes[index - window]

    if previous <= 0:
        return 0.0

    return round(((current / previous) - 1.0) * 100.0, 4)


def _target_return_pct(closes: list[float], index: int, horizon: int) -> float:
    if index + horizon >= len(closes):
        return 0.0

    current = closes[index]
    future = closes[index + horizon]

    if current <= 0:
        return 0.0

    return round(((future / current) - 1.0) * 100.0, 4)


def build_prediction_dataset(
    *,
    matrix: str | Path,
    prices_dir: str | Path,
    horizon: int = 5,
    min_history: int = 20,
) -> dict[str, Any]:
    matrix_rows = _read_csv(matrix)
    dataset_rows: list[dict[str, Any]] = []
    missing_price_files: list[str] = []

    for matrix_row in matrix_rows:
        ticker = str(matrix_row.get("ticker", "")).strip()
        sector = str(matrix_row.get("sector", "")).strip()

        price_file = _price_file_for_ticker(prices_dir, ticker)
        price_rows = _read_price_rows(price_file)

        if not price_rows:
            missing_price_files.append(ticker)
            continue

        closes = [_to_float(row["close"]) for row in price_rows]

        last_index = len(price_rows) - horizon - 1

        for index in range(min_history, last_index + 1):
            target_return = _target_return_pct(closes, index, horizon)

            row = {
                "date": price_rows[index]["date"],
                "ticker": ticker,
                "sector": sector,
                "return_1d": _return_pct(closes, index, 1),
                "return_5d": _return_pct(closes, index, 5),
                "return_20d": _return_pct(closes, index, 20),
                "volatility_20d": _to_float(matrix_row.get("volatility_20d")),
                "atr_pct": _to_float(matrix_row.get("atr_pct")),
                "trend_score": _to_float(matrix_row.get("trend_score")),
                "momentum_score": _to_float(matrix_row.get("momentum_score")),
                "news_score": _to_float(matrix_row.get("news_score"), 50.0),
                "market_trend": str(matrix_row.get("market_trend", "")),
                "market_volatility": str(matrix_row.get("market_volatility", "")),
                f"target_return_{horizon}d": target_return,
                f"target_up_{horizon}d": 1 if target_return > 0 else 0,
            }

            dataset_rows.append(row)

    columns = [
        *DATASET_COLUMNS,
        f"target_return_{horizon}d",
        f"target_up_{horizon}d",
    ]

    return {
        "matrix": str(matrix),
        "prices_dir": str(prices_dir),
        "horizon": horizon,
        "min_history": min_history,
        "rows": len(dataset_rows),
        "columns": columns,
        "missing_price_files": sorted(set(missing_price_files)),
        "missing_price_files_count": len(set(missing_price_files)),
        "dataset": dataset_rows,
    }


def write_prediction_dataset(
    *,
    matrix: str | Path,
    prices_dir: str | Path,
    output: str | Path,
    horizon: int = 5,
    min_history: int = 20,
) -> dict[str, Any]:
    payload = build_prediction_dataset(
        matrix=matrix,
        prices_dir=prices_dir,
        horizon=horizon,
        min_history=min_history,
    )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=payload["columns"])
        writer.writeheader()
        writer.writerows(payload["dataset"])

    payload["output"] = str(output_path)

    return payload



NUMERIC_FEATURES = [
    "return_1d",
    "return_5d",
    "return_20d",
    "volatility_20d",
    "atr_pct",
    "trend_score",
    "momentum_score",
    "news_score",
]

CATEGORICAL_MAPS = {
    "market_trend": {
        "DOWN": -1.0,
        "CHOPPY": 0.0,
        "UP": 1.0,
    },
    "market_volatility": {
        "LOW": -1.0,
        "NORMAL": 0.0,
        "HIGH": 1.0,
    },
}


def available_engines() -> list[str]:
    return available_legacy_engines()


def _parse_engines(engines: list[str] | None = None) -> list[str]:
    if not engines:
        return available_engines()

    allowed = set(available_engines())
    parsed = [engine.strip() for engine in engines if engine.strip()]
    unknown = [engine for engine in parsed if engine not in allowed]

    if unknown:
        raise ValueError(f"Unknown prediction engines: {', '.join(unknown)}")

    return parsed


def _feature_value(row: dict[str, Any], feature: str) -> float:
    if feature in CATEGORICAL_MAPS:
        value = str(row.get(feature, "")).upper()
        return CATEGORICAL_MAPS[feature].get(value, 0.0)

    return _to_float(row.get(feature), 0.0)


def _feature_vector(row: dict[str, Any]) -> list[float]:
    values = [_feature_value(row, feature) for feature in NUMERIC_FEATURES]
    values.append(_feature_value(row, "market_trend"))
    values.append(_feature_value(row, "market_volatility"))
    return values


def _target_values(rows: list[dict[str, Any]], target_column: str) -> list[int]:
    return [int(_to_float(row.get(target_column), 0.0)) for row in rows]


def _majority_prediction(train_rows: list[dict[str, Any]], target_column: str) -> int:
    if not train_rows:
        return 0

    up_rate = sum(_target_values(train_rows, target_column)) / len(train_rows)
    return 1 if up_rate >= 0.5 else 0


def _predict_momentum_rule(row: dict[str, Any]) -> int:
    momentum_score = _to_float(row.get("return_5d"), 0.0)
    trend_score = _to_float(row.get("trend_score"), 50.0)
    news_score = _to_float(row.get("news_score"), 50.0)

    return 1 if momentum_score > 0 and trend_score >= 45.0 and news_score >= 45.0 else 0


def _sigmoid(value: float) -> float:
    if value < -50:
        return 0.0

    if value > 50:
        return 1.0

    return 1.0 / (1.0 + math.exp(-value))


def _standardize_train(
    rows: list[dict[str, Any]],
) -> tuple[list[list[float]], list[float], list[float]]:
    raw = [_feature_vector(row) for row in rows]

    if not raw:
        return [], [], []

    width = len(raw[0])
    means: list[float] = []
    scales: list[float] = []

    for column in range(width):
        values = [item[column] for item in raw]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        scale = math.sqrt(variance) or 1.0

        means.append(mean)
        scales.append(scale)

    standardized = [
        [
            (row[column] - means[column]) / scales[column]
            for column in range(width)
        ]
        for row in raw
    ]

    return standardized, means, scales


def _standardize_row(
    row: dict[str, Any],
    means: list[float],
    scales: list[float],
) -> list[float]:
    raw = _feature_vector(row)

    return [
        (raw[column] - means[column]) / scales[column]
        for column in range(len(raw))
    ]


def _fit_logistic(
    train_rows: list[dict[str, Any]],
    target_column: str,
    *,
    epochs: int = 80,
    learning_rate: float = 0.05,
    l2: float = 0.01,
) -> dict[str, Any]:
    x_train, means, scales = _standardize_train(train_rows)
    y_train = _target_values(train_rows, target_column)

    if not x_train:
        return {
            "weights": [],
            "bias": 0.0,
            "means": means,
            "scales": scales,
        }

    width = len(x_train[0])
    weights = [0.0 for _ in range(width)]
    bias = 0.0

    for _ in range(epochs):
        for x_values, y_value in zip(x_train, y_train, strict=True):
            score = bias + sum(
                weight * value
                for weight, value in zip(weights, x_values, strict=True)
            )
            prediction = _sigmoid(score)
            error = prediction - y_value

            bias -= learning_rate * error

            for index in range(width):
                weights[index] -= learning_rate * (
                    error * x_values[index] + l2 * weights[index]
                )

    return {
        "weights": weights,
        "bias": bias,
        "means": means,
        "scales": scales,
    }


def _predict_logistic(model: dict[str, Any], row: dict[str, Any]) -> int:
    weights = list(model.get("weights", []))

    if not weights:
        return 0

    x_values = _standardize_row(
        row,
        list(model.get("means", [])),
        list(model.get("scales", [])),
    )
    score = float(model.get("bias", 0.0)) + sum(
        weight * value
        for weight, value in zip(weights, x_values, strict=True)
    )

    return 1 if _sigmoid(score) >= 0.5 else 0


def _candidate_thresholds(values: list[float], *, limit: int = 12) -> list[float]:
    unique = sorted(set(values))

    if len(unique) <= limit:
        return unique

    step = max(1, len(unique) // limit)

    return [unique[index] for index in range(step, len(unique), step)][:limit]


def _fit_stump(
    train_rows: list[dict[str, Any]],
    target_column: str,
    *,
    feature_subset: list[str] | None = None,
    sample_weight: list[float] | None = None,
) -> dict[str, Any]:
    features = feature_subset or NUMERIC_FEATURES
    y_values = _target_values(train_rows, target_column)

    if not train_rows:
        return {
            "feature": "return_5d",
            "threshold": 0.0,
            "direction": 1,
            "default": 0,
        }

    weights = sample_weight or [1.0 for _ in train_rows]
    default = _majority_prediction(train_rows, target_column)

    best_error = float("inf")
    best_model = {
        "feature": "return_5d",
        "threshold": 0.0,
        "direction": 1,
        "default": default,
    }

    for feature in features:
        values = [_feature_value(row, feature) for row in train_rows]

        for threshold in _candidate_thresholds(values):
            for direction in (1, -1):
                weighted_error = 0.0

                for value, actual, weight in zip(values, y_values, weights, strict=True):
                    prediction = 1 if direction * value >= direction * threshold else 0

                    if prediction != actual:
                        weighted_error += weight

                if weighted_error < best_error:
                    best_error = weighted_error
                    best_model = {
                        "feature": feature,
                        "threshold": threshold,
                        "direction": direction,
                        "default": default,
                    }

    return best_model


def _predict_stump(model: dict[str, Any], row: dict[str, Any]) -> int:
    value = _feature_value(row, str(model.get("feature", "return_5d")))
    threshold = float(model.get("threshold", 0.0))
    direction = int(model.get("direction", 1))

    return 1 if direction * value >= direction * threshold else 0


def _fit_bagged_stumps(
    train_rows: list[dict[str, Any]],
    target_column: str,
    *,
    estimators: int = 21,
) -> list[dict[str, Any]]:
    if not train_rows:
        return []

    rng = random.Random(42)
    models: list[dict[str, Any]] = []

    for index in range(estimators):
        sample = [
            train_rows[rng.randrange(len(train_rows))]
            for _ in range(len(train_rows))
        ]

        feature_subset = rng.sample(
            NUMERIC_FEATURES,
            k=min(4, len(NUMERIC_FEATURES)),
        )

        model = _fit_stump(
            sample,
            target_column,
            feature_subset=feature_subset,
        )
        model["estimator"] = index
        models.append(model)

    return models


def _predict_bagged_stumps(models: list[dict[str, Any]], row: dict[str, Any]) -> int:
    if not models:
        return 0

    votes = [_predict_stump(model, row) for model in models]
    return 1 if sum(votes) >= (len(votes) / 2) else 0


def _fit_boosted_stumps(
    train_rows: list[dict[str, Any]],
    target_column: str,
    *,
    estimators: int = 9,
) -> list[dict[str, Any]]:
    if not train_rows:
        return []

    weights = [1.0 / len(train_rows) for _ in train_rows]
    y_values = _target_values(train_rows, target_column)
    models: list[dict[str, Any]] = []

    for _ in range(estimators):
        model = _fit_stump(
            train_rows,
            target_column,
            sample_weight=weights,
        )

        predictions = [_predict_stump(model, row) for row in train_rows]
        error = sum(
            weight
            for weight, actual, prediction in zip(
                weights,
                y_values,
                predictions,
                strict=True,
            )
            if actual != prediction
        )
        error = min(max(error, 1e-6), 0.499999)
        alpha = 0.5 * math.log((1.0 - error) / error)

        new_weights: list[float] = []

        for weight, actual, prediction in zip(
            weights,
            y_values,
            predictions,
            strict=True,
        ):
            actual_signed = 1 if actual == 1 else -1
            predicted_signed = 1 if prediction == 1 else -1
            new_weights.append(
                weight * math.exp(-alpha * actual_signed * predicted_signed)
            )

        total_weight = sum(new_weights) or 1.0
        weights = [weight / total_weight for weight in new_weights]

        model["alpha"] = alpha
        models.append(model)

    return models


def _predict_boosted_stumps(models: list[dict[str, Any]], row: dict[str, Any]) -> int:
    if not models:
        return 0

    score = 0.0

    for model in models:
        prediction = _predict_stump(model, row)
        signed = 1 if prediction == 1 else -1
        score += float(model.get("alpha", 1.0)) * signed

    return 1 if score >= 0 else 0



def _metrics(
    *,
    rows: list[dict[str, Any]],
    predictions: list[int],
    target_column: str,
) -> dict[str, Any]:
    total = len(rows)

    if total == 0:
        return {
            "observations": 0,
            "accuracy": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "target_up_rate": 0.0,
            "predicted_up_rate": 0.0,
            "true_positive": 0,
            "true_negative": 0,
            "false_positive": 0,
            "false_negative": 0,
        }

    actual = [int(_to_float(row.get(target_column), 0.0)) for row in rows]

    true_positive = sum(1 for y, p in zip(actual, predictions, strict=True) if y == 1 and p == 1)
    true_negative = sum(1 for y, p in zip(actual, predictions, strict=True) if y == 0 and p == 0)
    false_positive = sum(1 for y, p in zip(actual, predictions, strict=True) if y == 0 and p == 1)
    false_negative = sum(1 for y, p in zip(actual, predictions, strict=True) if y == 1 and p == 0)

    accuracy = (true_positive + true_negative) / total
    precision_den = true_positive + false_positive
    recall_den = true_positive + false_negative

    precision = true_positive / precision_den if precision_den else 0.0
    recall = true_positive / recall_den if recall_den else 0.0

    return {
        "observations": total,
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "target_up_rate": round(sum(actual) / total, 4),
        "predicted_up_rate": round(sum(predictions) / total, 4),
        "true_positive": true_positive,
        "true_negative": true_negative,
        "false_positive": false_positive,
        "false_negative": false_negative,
    }


def walk_forward_evaluate(
    *,
    dataset: str | Path,
    horizon: int = 5,
    min_train_rows: int = 100,
    engines: list[str] | None = None,
    n_jobs: int = 4,
    autotune: bool = False,
    autotune_iter: int = 15,
    autotune_cv: int = 3,
) -> dict[str, Any]:
    rows = _read_csv(dataset)

    return evaluate_legacy_walk_forward(
        rows=rows,
        dataset=str(dataset),
        horizon=horizon,
        min_train_rows=min_train_rows,
        engines=engines,
        n_jobs=n_jobs,
        autotune=autotune,
        autotune_iter=autotune_iter,
        autotune_cv=autotune_cv,
    )


def write_evaluation_report(
    *,
    dataset: str | Path,
    output: str | Path,
    horizon: int = 5,
    min_train_rows: int = 100,
    engines: list[str] | None = None,
    n_jobs: int = 4,
    autotune: bool = False,
    autotune_iter: int = 15,
    autotune_cv: int = 3,
) -> dict[str, Any]:
    payload = walk_forward_evaluate(
        dataset=dataset,
        horizon=horizon,
        min_train_rows=min_train_rows,
        engines=engines,
        n_jobs=n_jobs,
        autotune=autotune,
        autotune_iter=autotune_iter,
        autotune_cv=autotune_cv,
    )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    payload["output"] = str(output_path)
    return payload


def run_prediction_lab(
    *,
    matrix: str | Path,
    prices_dir: str | Path,
    dataset_output: str | Path,
    evaluation_output: str | Path,
    horizon: int = 5,
    min_history: int = 20,
    min_train_rows: int = 100,
    engines: list[str] | None = None,
    n_jobs: int = 4,
    autotune: bool = False,
    autotune_iter: int = 15,
    autotune_cv: int = 3,
) -> dict[str, Any]:
    dataset_payload = write_prediction_dataset(
        matrix=matrix,
        prices_dir=prices_dir,
        output=dataset_output,
        horizon=horizon,
        min_history=min_history,
    )

    evaluation_payload = write_evaluation_report(
        dataset=dataset_output,
        output=evaluation_output,
        horizon=horizon,
        min_train_rows=min_train_rows,
        engines=engines,
        n_jobs=n_jobs,
        autotune=autotune,
        autotune_iter=autotune_iter,
        autotune_cv=autotune_cv,
    )

    models = evaluation_payload["models"]
    summary: dict[str, Any] = {
        "status": "OK",
        "engine_count": len(models),
        "best_accuracy_engine": None,
        "best_accuracy": None,
        "best_mae_engine": None,
        "best_mae": None,
    }

    if models:
        sorted_by_accuracy = sorted(
            models.items(),
            key=lambda item: (-item[1].get("accuracy", 0.0), item[1].get("mae_return", 0.0)),
        )
        summary["best_accuracy_engine"] = sorted_by_accuracy[0][0]
        summary["best_accuracy"] = sorted_by_accuracy[0][1].get("accuracy", 0.0)

        sorted_by_mae = sorted(
            models.items(),
            key=lambda item: (
                item[1].get("mae_return", float("inf")),
                -item[1].get("accuracy", 0.0),
            ),
        )
        summary["best_mae_engine"] = sorted_by_mae[0][0]
        summary["best_mae"] = sorted_by_mae[0][1].get("mae_return", 0.0)

    return {
        "status": "OK",
        "dataset": {
            "file": dataset_payload["output"],
            "rows": dataset_payload["rows"],
            "columns": len(dataset_payload["columns"]),
            "missing_price_files": dataset_payload["missing_price_files_count"],
        },
        "evaluation": {
            "file": evaluation_payload["output"],
            "rows": evaluation_payload["rows"],
            "evaluated_rows": evaluation_payload["evaluated_rows"],
            "n_jobs": evaluation_payload.get("n_jobs", n_jobs),
            "engines": evaluation_payload.get("engines", []),
            "engine_status": evaluation_payload.get("engine_status", {}),
            "autotune": evaluation_payload.get("autotune", {}),
            "models": evaluation_payload["models"],
        },
        "summary": summary,
    }


def render_prediction_dataset_summary(payload: dict[str, Any]) -> str:
    line = "-" * 100

    return "\n".join(
        [
            "PYMERCATOR PREDICTION DATASET",
            line,
            f"{'MATRIX':<22} {payload['matrix']}",
            f"{'PRICES DIR':<22} {payload['prices_dir']}",
            f"{'OUTPUT':<22} {payload.get('output', '-')}",
            f"{'HORIZON':<22} {payload['horizon']}",
            f"{'MIN HISTORY':<22} {payload['min_history']}",
            f"{'ROWS':<22} {payload['rows']}",
            f"{'COLUMNS':<22} {len(payload['columns'])}",
            f"{'MISSING PRICES':<22} {payload['missing_price_files_count']}",
        ]
    )


def render_evaluation_summary(payload: dict[str, Any]) -> str:
    line = "-" * 100
    lines = [
        "PYMERCATOR WALK-FORWARD EVALUATION",
        line,
        f"{'DATASET':<22} {payload['dataset']}",
        f"{'OUTPUT':<22} {payload.get('output', '-')}",
        f"{'HORIZON':<22} {payload['horizon']}",
        f"{'MIN TRAIN ROWS':<22} {payload['min_train_rows']}",
        f"{'N JOBS':<22} {payload.get('n_jobs', 4)}",
        f"{'ROWS':<22} {payload['rows']}",
        f"{'EVALUATED ROWS':<22} {payload['evaluated_rows']}",
        "",
        "ENGINE STATUS",
        line,
    ]

    for engine, status in payload.get("engine_status", {}).items():
        lines.append(f"{engine:<22} {status}")

    lines.extend(["", "MODELS", line])

    for engine, metrics in payload["models"].items():
        lines.append(
            f"{engine:<20} "
            f"acc={metrics['accuracy']:<7} "
            f"mae={metrics.get('mae_return', 0.0):<7} "
            f"prec={metrics['precision']:<7} "
            f"recall={metrics['recall']:<7} "
            f"obs={metrics['observations']}"
        )

    return "\n".join(lines)


def render_prediction_lab_summary(payload: dict[str, Any]) -> str:
    line = "-" * 100
    evaluation = payload["evaluation"]

    lines = [
        "PYMERCATOR PREDICTION LAB",
        line,
        f"{'STATUS':<22} {payload['status']}",
        f"{'DATASET FILE':<22} {payload['dataset']['file']}",
        f"{'DATASET ROWS':<22} {payload['dataset']['rows']}",
        f"{'EVALUATION FILE':<22} {evaluation['file']}",
        f"{'EVALUATED ROWS':<22} {evaluation['evaluated_rows']}",
        f"{'N JOBS':<22} {evaluation.get('n_jobs', 4)}",
        "",
        "ENGINE STATUS",
        line,
    ]

    for engine, status in evaluation.get("engine_status", {}).items():
        lines.append(f"{engine:<22} {status}")

    lines.extend(["", "MODELS", line])

    for engine, metrics in evaluation["models"].items():
        lines.append(
            f"{engine:<20} "
            f"acc={metrics['accuracy']:<7} "
            f"mae={metrics.get('mae_return', 0.0):<7} "
            f"prec={metrics['precision']:<7} "
            f"recall={metrics['recall']:<7} "
            f"obs={metrics['observations']}"
        )

    return "\n".join(lines)
