from pymercator.train_detail_report import render_train_detail_report
from pymercator.ui import strip_ansi


def _metrics(accuracy: float = 0.56) -> dict[str, object]:
    return {
        "observations": 10,
        "accuracy": accuracy,
        "precision": 0.55,
        "recall": 0.54,
        "false_positive_rate": 0.25,
        "false_negative_rate": 0.30,
        "target_up_rate": 0.52,
        "predicted_up_rate": 0.50,
        "quality_status": "OK",
        "optimal_threshold": 0.51,
        "confusion_matrix": {"TP": 3, "TN": 4, "FP": 2, "FN": 1},
        "calibrated_probability_stats": {
            "mean": 0.51,
            "std": 0.02,
            "p05": 0.47,
            "p50": 0.51,
            "p95": 0.55,
        },
    }


def _model(accuracy: float) -> dict[str, object]:
    return {
        "rows": 20,
        "evaluated_rows": 10,
        "status": "OK",
        "ensemble_metrics": _metrics(accuracy),
        "base_metrics": {
            "extratrees": _metrics(0.53),
            "randomforest": _metrics(0.54),
            "gradientboosting": _metrics(0.55),
        },
        "ridge_coefficients": {
            "weights": {
                "extratrees": 0.2,
                "randomforest": 0.3,
                "gradientboosting": 0.5,
            }
        },
        "optimal_threshold": 0.51,
    }


def test_train_detail_report_module_renders_expected_sections_without_dup_observer():
    payload = {
        "engine_used": "multi_horizon_ridge",
        "status": "OK",
        "model_quality": {
            "status": "WEAK",
            "edge": -0.01,
            "baseline_accuracy": 0.5,
        },
        "horizons": [5, 20, 60],
        "base_engines": ["extratrees", "randomforest", "gradientboosting"],
        "meta_model": "ridge",
        "horizon_models": {
            "D5": _model(0.51),
            "D20": _model(0.52),
            "D60": _model(0.53),
        },
        "asset_count_by_horizon": {"D5": 10, "D20": 10, "D60": 10},
        "horizon_observer": {
            "mode": "weighted",
            "scores": {"D5": 51.0, "D20": 52.0, "D60": 53.0},
            "weights": {"D5": 0.25, "D20": 0.35, "D60": 0.4},
            "combined_score": 52.15,
            "dominant_horizon": "D60",
            "behavior": "AVOID",
            "horizon_alignment": "FLAT",
            "dominance_strength": "NONE",
        },
    }

    output = strip_ansi(render_train_detail_report(payload))

    for section in (
        "GLOBAL SUMMARY",
        "HORIZON SCOREBOARD",
        "RIDGE WEIGHTS",
        "PROBABILITY PROFILE",
        "CONFUSION SUMMARY",
        "OBSERVER",
        "VERDICT",
    ):
        assert section in output
    assert output.splitlines().count("OBSERVER") == 1
