from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from pymercator.config_loader import deep_merge

SHORT_POLICY_SCHEMA = "short_policy.v1"
SHORT_THRESHOLDS_SCHEMA = "short_thresholds.v1"

DEFAULT_SHORT_POLICY: dict[str, Any] = {
    "schema_version": SHORT_POLICY_SCHEMA,
    "enabled": True,
    "mode": "MANUAL_ONLY",
    "allow_execution": False,
    "requires_borrow_data": True,
    "requires_cost_data": True,
    "requires_liquidity_check": True,
    "requires_squeeze_check": True,
    "requires_event_check": True,
    "allowed_trade_modes": ["SWING"],
    "default_direction": "SHORT",
    "never_enter_long_basket": True,
}

DEFAULT_SHORT_THRESHOLDS: dict[str, Any] = {
    "schema_version": SHORT_THRESHOLDS_SCHEMA,
    "setup": {
        "min_short_score": 70.0,
        "strong_short_score": 85.0,
        "max_trend": 40.0,
        "max_momentum": 40.0,
        "sector_weakness_required": False,
        "risk_off_bonus": True,
    },
    "risk": {
        "max_volatility": 55.0,
        "max_atr": 6.0,
        "max_gap_risk": 5.0,
        "max_single_name_exposure_pct": 5.0,
        "max_total_short_exposure_pct": 15.0,
    },
    "borrow": {
        "max_borrow_fee_pct": 5.0,
        "block_if_cost_unknown": True,
        "block_if_unavailable": True,
        "block_if_recall_risk_high": True,
        "manual_if_squeeze_risk_high": True,
    },
    "events": {
        "block_near_earnings_days": 3,
        "block_near_dividend_days": 3,
        "block_if_corporate_action": True,
    },
}


def _load_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_short_policy(path: str | Path = "config/short_policy.json") -> dict[str, Any]:
    payload = _load_json(path)
    if payload.get("schema_version") != SHORT_POLICY_SCHEMA:
        result = copy.deepcopy(DEFAULT_SHORT_POLICY)
        result["config_source"] = str(path)
        result["config_status"] = "DEFAULT"
        return result
    result = deep_merge(DEFAULT_SHORT_POLICY, payload)
    result["config_source"] = str(path)
    result["config_status"] = "OK"
    return result


def load_short_thresholds(path: str | Path = "config/short_thresholds.json") -> dict[str, Any]:
    payload = _load_json(path)
    if payload.get("schema_version") != SHORT_THRESHOLDS_SCHEMA:
        result = copy.deepcopy(DEFAULT_SHORT_THRESHOLDS)
        result["config_source"] = str(path)
        result["config_status"] = "DEFAULT"
        return result
    result = deep_merge(DEFAULT_SHORT_THRESHOLDS, payload)
    result["config_source"] = str(path)
    result["config_status"] = "OK"
    return result


def apply_legacy_short_overrides(
    *,
    policy: dict[str, Any],
    thresholds: dict[str, Any],
    position_actions_config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    short_config = (
        position_actions_config.get("short", {})
        if isinstance(position_actions_config, dict)
        else {}
    )
    if not isinstance(short_config, dict):
        return policy, thresholds

    result_policy = copy.deepcopy(policy)
    result_thresholds = copy.deepcopy(thresholds)
    setup = result_thresholds.setdefault("setup", {})
    risk = result_thresholds.setdefault("risk", {})
    borrow = result_thresholds.setdefault("borrow", {})

    if "enabled" in short_config:
        result_policy["enabled"] = bool(short_config.get("enabled"))
    if "mode" in short_config:
        result_policy["mode"] = str(short_config.get("mode") or result_policy["mode"]).upper()
    if "allow_execution" in short_config:
        result_policy["allow_execution"] = bool(short_config.get("allow_execution"))
    if "requires_borrow_data" in short_config:
        result_policy["requires_borrow_data"] = bool(short_config.get("requires_borrow_data"))
    if "min_short_score" in short_config:
        setup["min_short_score"] = float(short_config.get("min_short_score") or setup["min_short_score"])
    if "max_volatility" in short_config:
        risk["max_volatility"] = float(short_config.get("max_volatility") or risk["max_volatility"])
    if "max_atr" in short_config:
        risk["max_atr"] = float(short_config.get("max_atr") or risk["max_atr"])
    if "max_borrow_cost_pct" in short_config:
        borrow["max_borrow_fee_pct"] = float(
            short_config.get("max_borrow_cost_pct") or borrow["max_borrow_fee_pct"]
        )
    if short_config.get("block_without_borrow_data") is False:
        result_policy["requires_borrow_data"] = False
    return result_policy, result_thresholds
