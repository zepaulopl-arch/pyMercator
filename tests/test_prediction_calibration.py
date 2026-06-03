from __future__ import annotations

from typing import Any

from pymercator.cli_train import _model_quality, render_train_detail_report
from pymercator.legacy_prediction_engines import (
    fit_calibrated_legacy_classifier,
    metric_report,
    tune_probability_threshold,
)


def _rows(actual_up: list[int]) -> list[dict[str, Any]]:
    return [
        {
            "target_up_5d": value,
            "target_return_5d": 1.0 if value else -1.0,
        }
        for value in actual_up
    ]


def _brute_force_threshold(
    probabilities: list[float],
    actual_up: list[int],
    *,
    metric: str,
) -> dict[str, Any]:
    values = sorted({max(0.0, min(1.0, float(value))) for value in probabilities})
    candidates = {0.5, 0.0, 1.0, *values}
    for left, right in zip(values, values[1:], strict=False):
        candidates.add((left + right) / 2.0)

    def rate(numerator: float, denominator: float) -> float:
        return numerator / denominator if denominator else 0.0

    normalized_actual = [1 if value else 0 for value in actual_up]
    target_up_rate = sum(normalized_actual) / len(normalized_actual)
    best: tuple[float, float, float, float, float, float, int, dict[str, Any]] | None = None

    for candidate_index, threshold in enumerate(sorted(candidates)):
        predictions = [1 if value >= threshold else 0 for value in probabilities]
        pairs = list(zip(normalized_actual, predictions, strict=True))
        tp = sum(1 for actual, pred in pairs if actual and pred)
        tn = sum(1 for actual, pred in pairs if not actual and not pred)
        fp = sum(1 for actual, pred in pairs if not actual and pred)
        fn = sum(1 for actual, pred in pairs if actual and not pred)
        predicted_up_rate = sum(predictions) / len(predictions)
        recall = rate(tp, tp + fn)
        specificity = rate(tn, tn + fp)
        precision = rate(tp, tp + fp)
        false_positive_rate = rate(fp, fp + tn)
        accuracy = rate(tp + tn, len(predictions))

        if metric == "accuracy":
            score = accuracy
        elif metric == "f1":
            score = rate(2 * precision * recall, precision + recall)
        elif metric == "youden":
            score = round(recall - false_positive_rate, 6)
        else:
            score = round((recall + specificity) / 2.0, 6)

        is_degenerate = predicted_up_rate > 0.80 or predicted_up_rate < 0.20
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
                "metric": metric,
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

    return dict(best[-1])


def test_threshold_tuning_matches_brute_force_candidates():
    actual = [0, 1, 0, 1, 0, 1, 0]
    probabilities = [0.15, 0.2, 0.2, 0.55, 0.55, 0.8, 0.95]

    for metric in ["balanced_accuracy", "accuracy", "f1", "youden"]:
        assert tune_probability_threshold(probabilities, actual, metric=metric) == (
            _brute_force_threshold(probabilities, actual, metric=metric)
        )


def test_threshold_tuning_prevents_predicted_up_rate_collapse():
    actual = [0, 0, 0, 1, 1, 1]
    probabilities = [0.91, 0.92, 0.93, 0.94, 0.95, 0.96]

    fixed_predictions = [1 if value >= 0.5 else 0 for value in probabilities]
    fixed_metrics = metric_report(
        rows=_rows(actual),
        predictions_up=fixed_predictions,
        predictions_return=[0.0 for _ in actual],
        target_up_column="target_up_5d",
        target_return_column="target_return_5d",
    )
    assert fixed_metrics["predicted_up_rate"] == 1.0
    assert fixed_metrics["false_positive_rate"] == 1.0
    assert fixed_metrics["quality_status"] == "DEGENERATE"

    tuning = tune_probability_threshold(
        probabilities,
        actual,
        metric="balanced_accuracy",
    )
    tuned_predictions = [1 if value >= tuning["threshold"] else 0 for value in probabilities]
    tuned_metrics = metric_report(
        rows=_rows(actual),
        predictions_up=tuned_predictions,
        predictions_return=[0.0 for _ in actual],
        target_up_column="target_up_5d",
        target_return_column="target_return_5d",
        probabilities_up=probabilities,
        optimal_threshold=tuning["threshold"],
        threshold_tuning=tuning,
    )

    assert tuning["threshold"] > 0.5
    assert tuned_metrics["predicted_up_rate"] == 0.5
    assert tuned_metrics["false_positive_rate"] == 0.0
    assert tuned_metrics["quality_status"] == "OK"
    assert tuned_metrics["confusion_matrix"] == {"TP": 3, "TN": 3, "FP": 0, "FN": 0}
    assert "calibrated_probability_stats" in tuned_metrics
    assert "probability_distribution" in tuned_metrics


def test_fit_calibrated_classifier_uses_calibrated_classifier_cv(monkeypatch):
    import pymercator.legacy_prediction_engines as engines_mod

    calls: dict[str, Any] = {}

    class DummyClassifier:
        classes_ = [0, 1]

        def fit(self, _x_rows, _y_values):
            calls["raw_fit"] = True
            return self

        def predict_proba(self, x_rows):
            return [[0.4, 0.6] for _row in x_rows]

    class DummyCalibrated:
        classes_ = [0, 1]

        def __init__(self, classifier):
            self.classifier = classifier

        def fit(self, x_rows, y_values):
            calls["fit_rows"] = len(x_rows)
            calls["fit_classes"] = sorted(set(y_values))
            return self

        def predict_proba(self, x_rows):
            return [[0.45, 0.55] for _row in x_rows]

    def fake_make_classifier(engine, params, *, n_jobs=4):
        calls["engine"] = engine
        calls["params"] = params
        calls["n_jobs"] = n_jobs
        return DummyClassifier()

    def fake_make_calibrated(classifier, *, method, cv):
        calls["method"] = method
        calls["cv"] = cv
        return DummyCalibrated(classifier)

    monkeypatch.setattr(engines_mod, "_make_classifier", fake_make_classifier)
    monkeypatch.setattr(engines_mod, "_make_calibrated_classifier", fake_make_calibrated)

    model, meta = fit_calibrated_legacy_classifier(
        "extratrees",
        _rows([0, 1, 0, 1, 0, 1]),
        "target_up_5d",
        params={"n_estimators": 10},
        calibration={"enabled": True, "method": "isotonic", "cv": 5},
        n_jobs=2,
    )

    assert isinstance(model, DummyCalibrated)
    assert meta["status"] == "OK"
    assert meta["method"] == "isotonic"
    assert meta["cv"] == 3
    assert calls["method"] == "isotonic"
    assert calls["cv"] == 3
    assert calls["engine"] == "extratrees"
    assert calls["n_jobs"] == 2
    assert calls["fit_classes"] == [0, 1]


def test_calibrated_distribution_reduces_degeneration():
    actual = [0, 0, 0, 1, 1, 1]
    raw_probabilities = [0.91, 0.92, 0.93, 0.94, 0.95, 0.96]
    calibrated_probabilities = [0.20, 0.30, 0.40, 0.60, 0.70, 0.80]

    raw_metrics = metric_report(
        rows=_rows(actual),
        predictions_up=[1 if value >= 0.5 else 0 for value in raw_probabilities],
        predictions_return=[0.0 for _ in actual],
        target_up_column="target_up_5d",
        target_return_column="target_return_5d",
        probabilities_up=raw_probabilities,
        optimal_threshold=0.5,
    )

    tuning = tune_probability_threshold(calibrated_probabilities, actual)
    calibrated_metrics = metric_report(
        rows=_rows(actual),
        predictions_up=[
            1 if value >= tuning["threshold"] else 0
            for value in calibrated_probabilities
        ],
        predictions_return=[0.0 for _ in actual],
        target_up_column="target_up_5d",
        target_return_column="target_return_5d",
        probabilities_up=calibrated_probabilities,
        optimal_threshold=tuning["threshold"],
        threshold_tuning=tuning,
    )

    assert raw_metrics["quality_status"] == "DEGENERATE"
    assert calibrated_metrics["quality_status"] == "OK"
    assert raw_metrics["false_positive_rate"] == 1.0
    assert calibrated_metrics["false_positive_rate"] == 0.0


def test_model_quality_marks_and_clears_degenerate_status_after_calibration():
    observer = {"weights": {"D5": 1.0}}
    degenerate_horizons = {
        "D5": {
            "ensemble_metrics": {
                "accuracy": 0.60,
                "precision": 0.56,
                "recall": 1.0,
                "false_positive": 3,
                "true_negative": 0,
                "predicted_up_rate": 1.0,
                "quality_status": "DEGENERATE",
                "observations": 6,
            },
            "base_metrics": {
                "extratrees": {
                    "predicted_up_rate": 1.0,
                    "quality_status": "DEGENERATE",
                    "observations": 6,
                }
            },
        }
    }
    calibrated_horizons = {
        "D5": {
            "ensemble_metrics": {
                "accuracy": 0.60,
                "precision": 0.56,
                "recall": 0.60,
                "false_positive": 1,
                "true_negative": 2,
                "predicted_up_rate": 0.50,
                "quality_status": "OK",
                "observations": 6,
            },
            "base_metrics": {
                "extratrees": {
                    "predicted_up_rate": 0.50,
                    "quality_status": "OK",
                    "observations": 6,
                }
            },
        }
    }

    before = _model_quality(horizon_models=degenerate_horizons, observer=observer)
    after = _model_quality(horizon_models=calibrated_horizons, observer=observer)

    assert before["status"] == "DEGENERATE"
    assert before["degenerate"] is True
    assert after["status"] in {"OK", "STRONG"}
    assert after["degenerate"] is False


def test_train_detail_report_shows_degenerate_warning():
    report = render_train_detail_report(
        {
            "engine_used": "multi_horizon_ridge",
            "status": "OK",
            "operational": True,
            "horizons": [5],
            "base_engines": ["extratrees"],
            "meta_model": "ridge",
            "assets": 30,
            "model_quality": {
                "status": "DEGENERATE",
                "edge": -0.01,
                "baseline_accuracy": 0.5,
                "degenerate_warnings": [
                    {
                        "horizon": "D5",
                        "engine": "extratrees",
                        "predicted_up_rate": 0.99,
                    }
                ],
            },
            "horizon_observer": {
                "mode": "weighted",
                "scores": {"D5": 50.0},
                "weights": {"D5": 1.0},
                "combined_score": 50.0,
                "dominant_horizon": "D5",
                "behavior": "AVOID",
            },
            "asset_count_by_horizon": {"D5": 30},
            "horizon_models": {
                "D5": {
                    "status": "OK",
                    "engine_used": "ridge_ensemble",
                    "rows": 100,
                    "evaluated_rows": 20,
                    "optimal_threshold": 0.73,
                    "base_metrics": {},
                    "ridge_coefficients": {"intercept": 0.0, "weights": {}},
                    "ensemble_metrics": {
                        "observations": 20,
                        "accuracy": 0.5,
                        "precision": 0.5,
                        "recall": 1.0,
                        "false_positive_rate": 1.0,
                        "false_negative_rate": 0.0,
                        "target_up_rate": 0.5,
                        "predicted_up_rate": 1.0,
                        "mae_return": 0.0,
                        "quality_status": "DEGENERATE",
                        "confusion_matrix": {"TP": 10, "TN": 0, "FP": 10, "FN": 0},
                    },
                }
            },
        }
    )

    assert "DEGENERATE WARNING" in report
    assert "optimal_threshold" in report
