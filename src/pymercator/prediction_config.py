from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pymercator.config_loader import deep_merge

DEFAULT_OPERATIONAL_CONFIG: dict[str, Any] = {
    "default_engine": "multi_horizon_ridge",
    "per_horizon_engine": "ridge_ensemble",
    "horizons": [5, 20, 60],
    "base_engines": ["extratrees", "randomforest", "gradientboosting"],
    "meta_model": "ridge",
    "observer_mode": "weighted",
    "weights": {
        "D5": 0.25,
        "D20": 0.35,
        "D60": 0.40,
    },
    "min_assets": 30,
    "min_rows_per_horizon": 100,
    "min_history": 120,
    "min_train_rows": 100,
    "n_jobs": 4,
    "autotune": False,
    "autotune_iter": 20,
    "autotune_cv": 3,
    "calibration": {
        "enabled": True,
        "method": "sigmoid",
        "cv": 3,
        "threshold_metric": "balanced_accuracy",
    },
}

DEFAULT_EXPERIMENTAL_CONFIG: dict[str, Any] = {
    "allow_custom_horizons": False,
    "allow_custom_engines": False,
    "allow_small_universe": False,
}

DEFAULT_AUTOTUNE_AUDIT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "mode": "random_search",
    "n_iter": 20,
    "cv_splits": 3,
    "walk_forward": True,
    "audit": True,
}

DEFAULT_EXPERIMENTAL_ENGINES_CONFIG: dict[str, Any] = {
    "enabled": False,
    "include": [
        "histgradientboosting",
        "logistic_elasticnet",
        "sgd_logloss_calibrated",
        "adaboost",
    ],
    "optional": [],
}

DEFAULT_AVAILABLE_ENGINES_CONFIG: dict[str, Any] = {
    "extratrees": {},
    "randomforest": {},
    "gradientboosting": {},
    "histgradientboosting": {},
    "logistic_elasticnet": {},
    "sgd_logloss_calibrated": {},
    "adaboost": {},
}

DEFAULT_PREDICTION_CONFIG: dict[str, Any] = {
    "operational": DEFAULT_OPERATIONAL_CONFIG,
    "available_engines": DEFAULT_AVAILABLE_ENGINES_CONFIG,
    "experimental": DEFAULT_EXPERIMENTAL_CONFIG,
    "autotune": DEFAULT_AUTOTUNE_AUDIT_CONFIG,
    "experimental_engines": DEFAULT_EXPERIMENTAL_ENGINES_CONFIG,
}


def horizon_key(horizon: int) -> str:
    return f"D{int(horizon)}"


def parse_horizons(value: str | list[int] | tuple[int, ...] | None) -> list[int]:
    if value is None or value == "":
        return []
    if isinstance(value, list | tuple):
        return [int(item) for item in value]
    return [int(item.strip()) for item in str(value).split(",") if item.strip()]


def parse_list(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list | tuple):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    return [item.strip().lower() for item in str(value).split(",") if item.strip()]


def parse_weights(value: str | dict[str, float] | None) -> dict[str, float]:
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return {_weight_key(str(key)): float(item) for key, item in value.items()}

    weights: dict[str, float] = {}
    for part in str(value).split(","):
        if not part.strip():
            continue
        key, raw = part.split("=", 1)
        weights[_weight_key(key)] = float(raw.strip())
    return weights


def normalize_calibration_config(value: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    method = str(payload.get("method", "sigmoid")).strip().lower()
    if method in {"platt", "platt_scaling"}:
        method = "sigmoid"
    if method not in {"sigmoid", "isotonic"}:
        method = "sigmoid"

    metric = str(payload.get("threshold_metric", "balanced_accuracy")).strip().lower()
    if metric not in {"balanced_accuracy", "accuracy", "f1", "youden"}:
        metric = "balanced_accuracy"

    return {
        "enabled": bool(payload.get("enabled", True)),
        "method": method,
        "cv": max(2, int(payload.get("cv", 3) or 3)),
        "threshold_metric": metric,
    }


def _weight_key(value: str) -> str:
    key = value.strip().upper()
    return f"D{key}" if key.isdigit() else key


def _legacy_to_structured(payload: dict[str, Any]) -> dict[str, Any]:
    if "operational" in payload:
        return payload

    operational = json.loads(json.dumps(DEFAULT_OPERATIONAL_CONFIG))
    operational.update(
        {
            "horizons": payload.get("horizons", operational["horizons"]),
            "default_engine": payload.get(
                "default_engine",
                operational["default_engine"],
            ),
            "per_horizon_engine": payload.get(
                "per_horizon_engine",
                operational["per_horizon_engine"],
            ),
            "base_engines": payload.get("base_engines", operational["base_engines"]),
            "meta_model": payload.get("meta_model", operational["meta_model"]),
            "observer_mode": payload.get("observer", {}).get(
                "mode",
                operational["observer_mode"],
            ),
            "weights": payload.get("observer", {}).get("weights", operational["weights"]),
        }
    )
    training = payload.get("training", {})
    for key in (
        "min_history",
        "min_train_rows",
        "min_rows_per_horizon",
        "n_jobs",
        "autotune",
        "autotune_iter",
        "autotune_cv",
    ):
        if key in training:
            operational[key] = training[key]
    if "min_assets" in payload:
        operational["min_assets"] = payload["min_assets"]
    if "min_rows_per_horizon" in payload:
        operational["min_rows_per_horizon"] = payload["min_rows_per_horizon"]

    return {
        "operational": operational,
        "experimental": payload.get("experimental", DEFAULT_EXPERIMENTAL_CONFIG),
    }


def load_prediction_config(path: str | Path = "config/prediction.json") -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return json.loads(json.dumps(DEFAULT_PREDICTION_CONFIG))

    payload = json.loads(file_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("prediction config must be a JSON object")

    return deep_merge(DEFAULT_PREDICTION_CONFIG, _legacy_to_structured(payload))


def effective_prediction_config(
    *,
    path: str | Path = "config/prediction.json",
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_config = load_prediction_config(path)
    operational = raw_config["operational"]
    experimental = raw_config["experimental"]
    overrides = overrides or {}

    config: dict[str, Any] = {
        "mode": "operational",
        "default_engine": str(
            operational.get("default_engine", "multi_horizon_ridge")
        ).strip(),
        "per_horizon_engine": str(
            operational.get("per_horizon_engine", "ridge_ensemble")
        ).strip(),
        "operational_defaults": json.loads(json.dumps(operational)),
        "experimental_policy": json.loads(json.dumps(experimental)),
        "horizons": list(operational["horizons"]),
        "base_engines": list(operational["base_engines"]),
        "meta_model": str(operational["meta_model"]).strip().lower(),
        "min_assets": int(operational.get("min_assets", 30)),
        "min_rows_per_horizon": int(operational.get("min_rows_per_horizon", 100)),
        "observer": {
            "mode": str(operational.get("observer_mode", "weighted")).strip().lower(),
            "weights": parse_weights(operational.get("weights", {})),
            "independent_analysis": True,
            "combined_analysis": True,
        },
        "calibration": normalize_calibration_config(operational.get("calibration", {})),
        "training": {
            "min_history": int(operational.get("min_history", 120)),
            "min_train_rows": int(operational.get("min_train_rows", 100)),
            "n_jobs": int(operational.get("n_jobs", 4)),
            "autotune": bool(operational.get("autotune", False)),
            "autotune_iter": int(operational.get("autotune_iter", 20)),
            "autotune_cv": int(operational.get("autotune_cv", 3)),
            "temporal_split": True,
            "shuffle": False,
        },
    }

    if overrides.get("horizons"):
        config["horizons"] = parse_horizons(overrides["horizons"])

    if overrides.get("base_engines"):
        config["base_engines"] = parse_list(overrides["base_engines"])

    if overrides.get("meta_model"):
        config["meta_model"] = str(overrides["meta_model"]).strip().lower()

    observer = config.setdefault("observer", {})
    if overrides.get("observer_mode"):
        observer["mode"] = str(overrides["observer_mode"]).strip().lower()
    if overrides.get("weights"):
        observer["weights"] = parse_weights(overrides["weights"])
    if overrides.get("independent_horizons") is True:
        observer["independent_analysis"] = True
    if overrides.get("combined_horizons") is True:
        observer["combined_analysis"] = True

    training = config.setdefault("training", {})
    for key in ("min_history", "min_train_rows", "n_jobs", "autotune_iter", "autotune_cv"):
        if overrides.get(key) is not None:
            training[key] = int(overrides[key])
    if overrides.get("autotune") is not None:
        training["autotune"] = bool(overrides["autotune"])

    calibration = config.setdefault("calibration", {})
    if overrides.get("calibration_enabled") is not None:
        calibration["enabled"] = bool(overrides["calibration_enabled"])
    if overrides.get("calibration_method"):
        calibration["method"] = str(overrides["calibration_method"]).strip().lower()
    if overrides.get("calibration_cv") is not None:
        calibration["cv"] = int(overrides["calibration_cv"])
    if overrides.get("threshold_metric"):
        calibration["threshold_metric"] = str(overrides["threshold_metric"]).strip().lower()
    config["calibration"] = normalize_calibration_config(calibration)

    return config
