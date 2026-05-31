from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_PRESETS: dict[str, Any] = {
    "default_profile": "daily",
    "paths": {
        "indices_catalog": "config/indices_catalog.json",
        "indices_dir": "data/indices",
        "prices_dir": "data/prices",
        "sentiment_dir": "data/sentiment",
        "tickers_file": "data/universes/ibov_tickers.csv",
        "universe_output": "data/universes/ibov_live.csv",
        "context_output": "config/market_context_auto.json",
        "features_catalog": "config/features_catalog.json",
        "feature_matrix": "storage/features/latest_feature_matrix.csv",
        "prediction_dataset": "storage/prediction/latest_prediction_dataset.csv",
        "prediction_evaluation": "storage/prediction/latest_evaluation.json",
        "scenario_runs": "storage/scenario_runs",
    },
    "prediction": {
        "horizon": 5,
        "min_history": 20,
        "min_train_rows": 100,
        "n_jobs": 4,
        "engines": [
            "ridge_ensemble",
        ],
        "autotune": False,
        "autotune_iter": 15,
        "autotune_cv": 3,
    },
    "daily": {
        "skip_indices_fetch": False,
        "skip_asset_fetch": False,
    },
    "fast": {
        "skip_indices_fetch": True,
        "skip_asset_fetch": True,
        "prediction_engines": [
            "rolling_majority",
        ],
    },
    "lab": {
        "skip_indices_fetch": True,
        "skip_asset_fetch": True,
    },
    "profiles": {
        "daily": {
            "skip_indices_fetch": False,
            "skip_asset_fetch": False,
        },
        "no_fetch": {
            "skip_indices_fetch": True,
            "skip_asset_fetch": True,
        },
        "fast": {
            "skip_indices_fetch": True,
            "skip_asset_fetch": True,
            "prediction_engines": [
                "rolling_majority",
            ],
        },
        "lab": {
            "skip_indices_fetch": True,
            "skip_asset_fetch": True,
        },
    },
    "ui": {
        "theme": "BBG-DARK",
        "width": 120,
        "compact": True,
    },
}


def load_presets(path: str | Path = "config/pymercator_presets.json") -> dict[str, Any]:
    file_path = Path(path)

    if not file_path.exists():
        return DEFAULT_PRESETS.copy()

    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_PRESETS.copy()


def resolve_profile(
    name: str | None = None,
    path: str | Path = "config/pymercator_presets.json",
) -> dict[str, Any]:
    presets = load_presets(path)
    profile_name = name or presets.get("default_profile")

    # Merge global and profile-specific keys
    result: dict[str, Any] = {}
    result["paths"] = presets.get("paths", {}).copy()
    result["prediction"] = presets.get("prediction", {}).copy()
    result["daily"] = presets.get("daily", {}).copy()
    result["ui"] = presets.get("ui", {}).copy()

    profile_section = {}
    if profile_name:
        profile_section = presets.get("profiles", {}).get(profile_name, {})
        if not profile_section:
            profile_section = presets.get(profile_name, {})

    # shallow merge known sections
    for key in ("paths", "prediction", "daily", "ui"):
        if isinstance(profile_section.get(key), dict):
            result[key].update(profile_section.get(key, {}))

    for key in ("skip_indices_fetch", "skip_asset_fetch"):
        if key in profile_section:
            result["daily"][key] = profile_section[key]

    if "prediction_engines" in profile_section:
        result["prediction"]["engines"] = list(profile_section["prediction_engines"])

    result["profile"] = profile_name
    return result


def get_default_paths(path: str | Path = "config/pymercator_presets.json") -> dict[str, str]:
    return resolve_profile(None, path).get("paths", {})


def get_prediction_defaults(
    profile: str | None = None,
    path: str | Path = "config/pymercator_presets.json",
) -> dict[str, Any]:
    return resolve_profile(profile, path).get("prediction", {})


def resolve_effective_config(
    profile: str | None = None,
    overrides: dict | None = None,
    path: str | Path = "config/pymercator_presets.json",
) -> dict[str, Any]:
    """Return the effective configuration resolving profile and applying overrides.

    The result is a dict with keys: `paths`, `prediction`, `daily`, `ui`, `profile`.
    """
    base = resolve_profile(profile, path)
    overrides = overrides or {}

    result: dict[str, Any] = {}
    # shallow merge known sections
    for key in ("paths", "prediction", "daily", "ui"):
        section = base.get(key, {}).copy()
        if isinstance(overrides.get(key), dict):
            section.update(overrides.get(key, {}))
        result[key] = section

    result["profile"] = overrides.get("profile", base.get("profile"))

    # allow top-level overrides for prediction keys
    if isinstance(overrides.get("prediction"), dict):
        result["prediction"].update(overrides.get("prediction", {}))

    return result
