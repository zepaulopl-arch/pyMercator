from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_PREDICTION_CONFIG: dict[str, Any] = {
    "default_engine": "multi_horizon_ridge",
    "horizons": [5, 20, 60],
    "base_engines": ["extratrees", "randomforest", "gradientboosting"],
    "meta_model": "ridge",
    "observer": {
        "mode": "weighted",
        "weights": {
            "D5": 0.25,
            "D20": 0.35,
            "D60": 0.40,
        },
        "independent_analysis": True,
        "combined_analysis": True,
    },
    "training": {
        "min_history": 120,
        "min_train_rows": 100,
        "n_jobs": 4,
        "autotune": False,
        "autotune_iter": 20,
        "autotune_cv": 3,
        "temporal_split": True,
        "shuffle": False,
    },
    "fallback": {
        "allow_baseline": True,
        "baseline_engine": "rolling_majority",
        "baseline_requires_explicit_request": True,
    },
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
        return {
            _weight_key(str(key)): float(item)
            for key, item in value.items()
        }

    weights: dict[str, float] = {}
    for part in str(value).split(","):
        if not part.strip():
            continue
        key, raw = part.split("=", 1)
        weights[_weight_key(key)] = float(raw.strip())
    return weights


def _weight_key(value: str) -> str:
    key = value.strip().upper()
    return f"D{key}" if key.isdigit() else key


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(base))
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_prediction_config(path: str | Path = "config/prediction.json") -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return json.loads(json.dumps(DEFAULT_PREDICTION_CONFIG))

    payload = json.loads(file_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("prediction config must be a JSON object")
    return _deep_merge(DEFAULT_PREDICTION_CONFIG, payload)


def effective_prediction_config(
    *,
    path: str | Path = "config/prediction.json",
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = load_prediction_config(path)
    overrides = overrides or {}

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

    return config
