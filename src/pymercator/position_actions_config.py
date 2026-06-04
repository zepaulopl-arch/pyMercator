from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from pymercator.config_loader import deep_merge

CONFIG_SCHEMA_VERSION = "position_actions_config.v1"

DEFAULT_POSITION_ACTIONS_CONFIG: dict[str, Any] = {
    "schema_version": CONFIG_SCHEMA_VERSION,
    "exit": {
        "take_profit_pct": 8.0,
        "reduce_profit_pct": 4.0,
        "stop_loss_pct": -3.0,
        "trail_profit_pct": 5.0,
        "risk_off_reduce": True,
        "model_weak_reduce": True,
        "behavior_avoid_reduce": True,
        "vol_high_pct": 8.0,
        "atr_high_pct": 6.0,
    },
    "short": {
        "enabled": True,
        "observational_only": True,
        "min_short_score": 65.0,
        "requires_borrow_data": True,
        "block_without_borrow_data": True,
        "borrow_data_path": "storage/borrow/latest_borrow_data.csv",
        "max_borrow_cost_pct": 5.0,
        "min_available_qty": 1.0,
        "max_squeeze_risk": 70.0,
        "max_volatility": 60.0,
        "max_atr": 7.0,
    },
    "hedge": {
        "enabled": True,
        "observational_only": True,
        "risk_off_hedge_candidate": True,
    },
    "manual_review": {
        "position_outside_universe": True,
    },
}


def default_position_actions_config() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_POSITION_ACTIONS_CONFIG)


def load_position_actions_config(
    path: str | Path = "config/position_actions.json",
) -> dict[str, Any]:
    default = default_position_actions_config()
    source = Path(path)
    if not source.exists():
        default["config_source"] = str(source)
        default["config_status"] = "DEFAULT"
        return default

    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        default["config_source"] = str(source)
        default["config_status"] = "DEFAULT"
        default["config_warning"] = f"unable to load position actions config: {exc}"
        return default

    if not isinstance(payload, dict):
        default["config_source"] = str(source)
        default["config_status"] = "DEFAULT"
        default["config_warning"] = "position actions config must be a JSON object"
        return default

    if payload.get("schema_version") != CONFIG_SCHEMA_VERSION:
        default["config_source"] = str(source)
        default["config_status"] = "DEFAULT"
        default["config_warning"] = (
            "unsupported position actions config schema_version: "
            f"{payload.get('schema_version', '-')}"
        )
        return default

    merged = deep_merge(default, payload)
    merged["config_source"] = str(source)
    merged["config_status"] = "OK"
    return merged
