from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MARKET_CONTEXT_SCHEMA = "market_context.v2"
THRESHOLDS_SCHEMA = "market_context_thresholds.v1"
CONFIG_SCHEMA = "market_context_config.v1"

DEFAULT_CONTEXT_CONFIG: dict[str, Any] = {
    "schema_version": CONFIG_SCHEMA,
    "enabled": True,
    "sources": {
        "bcb": True,
        "b3": True,
        "cvm": True,
        "market_data": True,
        "commodities": True,
        "manual": True,
    },
    "manual_context": "storage/context/manual_market_context.json",
    "freshness": {"max_ok_days": 3, "max_warning_days": 7},
}

DEFAULT_THRESHOLDS: dict[str, Any] = {
    "schema_version": THRESHOLDS_SCHEMA,
    "weights": {
        "market_trend": 0.25,
        "market_volatility": 0.20,
        "rates": 0.15,
        "fx": 0.15,
        "commodities": 0.15,
        "events": 0.10,
    },
    "regime": {
        "risk_on_min_score": 65.0,
        "risk_off_max_score": 45.0,
        "choppy_min_volatility": 55.0,
    },
    "freshness": {"max_ok_days": 3, "max_warning_days": 7},
    "sector_drivers": {
        "financials": ["rates", "credit", "fiscal"],
        "materials": ["iron_ore", "china", "usdbrl"],
        "energy": ["oil", "geopolitics", "usdbrl"],
        "utilities": ["rates", "regulation"],
        "consumer_discretionary": ["rates", "credit", "income"],
        "consumer_staples": ["inflation", "income", "usdbrl"],
        "real_estate": ["rates", "credit"],
        "industrials": ["activity", "usdbrl"],
        "health_care": ["rates", "regulation"],
        "communication": ["rates", "defensive"],
    },
}


def _deep_merge(default: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(default)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_market_context_config(
    path: str | Path = "config/market_context.json",
) -> dict[str, Any]:
    payload = _read_json(path)
    if payload.get("schema_version") != CONFIG_SCHEMA:
        return copy.deepcopy(DEFAULT_CONTEXT_CONFIG)
    return _deep_merge(DEFAULT_CONTEXT_CONFIG, payload)


def load_market_context_thresholds(
    path: str | Path = "config/market_context_thresholds.json",
) -> dict[str, Any]:
    payload = _read_json(path)
    if payload.get("schema_version") != THRESHOLDS_SCHEMA:
        return copy.deepcopy(DEFAULT_THRESHOLDS)
    return _deep_merge(DEFAULT_THRESHOLDS, payload)


def _tags(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip().upper() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip().upper() for item in value if str(item).strip()]
    return []


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in values if item))


def _risk_value(payload: dict[str, Any], key: str, default: str = "UNKNOWN") -> str:
    value = str(payload.get(key, default) or default).upper()
    allowed = {"LOW", "MEDIUM", "HIGH", "EXTREME", "UNKNOWN"}
    return value if value in allowed else default


def manual_overrides_from_context(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") == MARKET_CONTEXT_SCHEMA:
        overrides = payload.get("manual_overrides", {})
        if isinstance(overrides, dict):
            return {
                "headline_tags": _tags(overrides.get("headline_tags")),
                "notes": str(overrides.get("notes", "")),
                "geopolitical_risk": _risk_value(overrides, "geopolitical_risk"),
                "domestic_policy_risk": _risk_value(overrides, "domestic_policy_risk"),
                "fiscal_risk": _risk_value(overrides, "fiscal_risk"),
            }
    return {
        "headline_tags": _tags(payload.get("headline_tags")),
        "notes": str(payload.get("notes", "")),
        "geopolitical_risk": _risk_value(payload, "geopolitical_risk", "UNKNOWN"),
        "domestic_policy_risk": _risk_value(payload, "domestic_policy_risk", "UNKNOWN"),
        "fiscal_risk": _risk_value(payload, "fiscal_risk", "UNKNOWN"),
    }


def _manual_overrides(
    *,
    manual_context_path: str | Path | None,
    previous_context: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    manual_payload = _read_json(manual_context_path) if manual_context_path else {}
    if manual_payload:
        return "OK", manual_overrides_from_context(manual_payload)
    if previous_context:
        overrides = manual_overrides_from_context(previous_context)
        if overrides["headline_tags"] or overrides["notes"]:
            return "OK", overrides
    return "PARTIAL", manual_overrides_from_context({})


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _trend_from_return(value: float) -> str:
    if value >= 2.0:
        return "UP"
    if value <= -2.0:
        return "DOWN"
    return "CHOPPY"


def _stress_from_return(value: float, *, medium: float, high: float) -> str:
    absolute = abs(value)
    if absolute >= high:
        return "HIGH"
    if absolute >= medium:
        return "MEDIUM"
    return "LOW"


def _volatility_bucket(value: float) -> str:
    if value >= 28.0:
        return "HIGH"
    if 0.0 < value <= 12.0:
        return "LOW"
    return "NORMAL" if value > 0 else "UNKNOWN"


def _score_from_bucket(value: str, scores: dict[str, float]) -> float:
    return scores.get(str(value).upper(), scores.get("UNKNOWN", 45.0))


def _context_score(
    *,
    market_trend: str,
    market_volatility: str,
    fx_stress: str,
    brent_stress: str,
    events: dict[str, Any],
    thresholds: dict[str, Any],
) -> float:
    weights = thresholds.get("weights", {})
    raw = {
        "market_trend": _score_from_bucket(
            market_trend,
            {"UP": 80.0, "CHOPPY": 52.0, "DOWN": 25.0, "UNKNOWN": 40.0},
        ),
        "market_volatility": _score_from_bucket(
            market_volatility,
            {"LOW": 72.0, "NORMAL": 62.0, "HIGH": 25.0, "UNKNOWN": 45.0},
        ),
        "rates": 50.0,
        "fx": _score_from_bucket(
            fx_stress,
            {"LOW": 68.0, "MEDIUM": 48.0, "HIGH": 25.0, "UNKNOWN": 45.0},
        ),
        "commodities": _score_from_bucket(
            brent_stress,
            {"LOW": 62.0, "MEDIUM": 50.0, "HIGH": 35.0, "UNKNOWN": 45.0},
        ),
        "events": 60.0,
    }
    if events.get("geopolitical_risk") in {"HIGH", "EXTREME"}:
        raw["events"] = 25.0
    if events.get("fiscal_risk") == "HIGH":
        raw["rates"] = 30.0

    total_weight = sum(_float(value, 0.0) for value in weights.values()) or 1.0
    score = sum(
        raw[key] * (_float(weights.get(key), 0.0) / total_weight)
        for key in raw
    )
    return round(max(0.0, min(100.0, score)), 2)


def _regime_from_score(score: float, market_trend: str, market_volatility: str, thresholds: dict[str, Any]) -> str:
    regime = thresholds.get("regime", {})
    if market_trend == "UP" and score >= _float(regime.get("risk_on_min_score"), 65.0):
        return "RISK_ON"
    if market_trend == "DOWN" or market_volatility == "HIGH" or score <= _float(regime.get("risk_off_max_score"), 45.0):
        return "RISK_OFF"
    return "CHOPPY"


def _sector_context(
    *,
    drivers: dict[str, list[str]],
    fx_stress: str,
    brent_stress: str,
    fiscal_risk: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for sector, items in drivers.items():
        context = "NEUTRAL"
        reason = "baseline"
        if sector in {"financials", "utilities", "consumer_discretionary", "real_estate"} and fiscal_risk == "HIGH":
            context = "CAUTION"
            reason = "fiscal/rates"
        elif sector == "energy" and brent_stress in {"MEDIUM", "HIGH"}:
            context = "CAUTION" if brent_stress == "HIGH" else "NEUTRAL"
            reason = "oil/geopolitics"
        elif sector == "materials" and fx_stress == "HIGH":
            context = "CAUTION"
            reason = "usdbrl volatility"
        result[sector] = {
            "macro_driver": str(items[0]) if items else "unknown",
            "context": context,
            "reason": reason,
        }
    return result


def build_market_context(
    *,
    auto_context: dict[str, Any],
    thresholds: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    manual_context_path: str | Path | None = None,
    previous_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or load_market_context_thresholds()
    config = config or load_market_context_config()
    manual_status, manual = _manual_overrides(
        manual_context_path=manual_context_path,
        previous_context=previous_context,
    )

    metrics = auto_context.get("metrics", {}) if isinstance(auto_context, dict) else {}
    market_trend = str(auto_context.get("market_trend", "UNKNOWN")).upper()
    market_volatility = str(auto_context.get("market_volatility", "UNKNOWN")).upper()
    headline_tags = _dedupe_preserve_order(
        _tags(auto_context.get("headline_tags")) + manual["headline_tags"]
    )
    notes = "; ".join(item for item in [str(auto_context.get("notes", "")), manual["notes"]] if item)

    usdbrl_ret_20 = _float(metrics.get("usdbrl_return_20d_pct"), 0.0)
    brent_ret_20 = _float(metrics.get("brent_return_20d_pct"), 0.0)
    ibov_vol_20 = _float(metrics.get("ibov_volatility_20d_annualized_pct"), 0.0)
    fx_stress = _stress_from_return(usdbrl_ret_20, medium=3.0, high=6.0)
    brent_stress = _stress_from_return(brent_ret_20, medium=5.0, high=10.0)
    events = {
        "headline_tags": headline_tags,
        "manual_notes": manual["notes"],
        "geopolitical_risk": manual["geopolitical_risk"],
        "domestic_policy_risk": manual["domestic_policy_risk"],
        "fiscal_risk": manual["fiscal_risk"],
    }
    score = _context_score(
        market_trend=market_trend,
        market_volatility=market_volatility,
        fx_stress=fx_stress,
        brent_stress=brent_stress,
        events=events,
        thresholds=thresholds,
    )
    regime = _regime_from_score(score, market_trend, market_volatility, thresholds)
    quality = "OK" if auto_context else "FAIL"
    if manual_status == "PARTIAL":
        quality = "OK" if quality == "OK" else quality

    context_sources = {
        "auto": "OK" if auto_context else "FAIL",
        "thresholds": "OK" if thresholds.get("schema_version") == THRESHOLDS_SCHEMA else "PARTIAL",
        "manual": manual_status,
        "bcb": "UNKNOWN",
        "b3": "UNKNOWN",
        "cvm": "UNKNOWN",
        "market_data": "OK" if auto_context else "FAIL",
        "commodities": "OK" if metrics.get("brent_return_20d_pct") is not None else "UNKNOWN",
    }

    source_config = config.get("sources", {}) if isinstance(config, dict) else {}
    for source in ("bcb", "b3", "cvm"):
        if not bool(source_config.get(source, True)):
            context_sources[source] = "UNKNOWN"

    drivers = ["ibov", "usdbrl", "oil"]
    risks: list[str] = []
    if market_volatility == "HIGH":
        risks.append("market volatility")
    if fx_stress != "LOW":
        risks.append("usdbrl")
    if brent_stress == "HIGH" or "OIL_STRESS" in headline_tags:
        risks.append("oil")
    if manual["geopolitical_risk"] in {"HIGH", "EXTREME"}:
        risks.append("geopolitics")

    return {
        "schema_version": MARKET_CONTEXT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_date": None,
        "context_sources": context_sources,
        "thresholds_version": str(thresholds.get("schema_version", THRESHOLDS_SCHEMA)),
        "manual_overrides": manual,
        "freshness": {
            "max_staleness_days": 0,
            "freshness_status": "OK" if auto_context else "FAIL",
            "data_quality_score": 100.0 if auto_context else 0.0,
        },
        "macro": {
            "selic": {"current": None, "source": "BCB_SGS", "last_update": None, "staleness_days": None},
            "copom": {"last_decision": None, "next_meeting_date": None, "tone": "UNKNOWN", "source": "BCB_COPOM"},
            "focus": {
                "ipca_current_year": None,
                "ipca_next_year": None,
                "selic_current_year": None,
                "selic_next_year": None,
                "usdbrl_current_year": None,
                "gdp_current_year": None,
                "source": "BCB_FOCUS",
            },
        },
        "fx": {
            "usdbrl": {
                "last": None,
                "trend": _trend_from_return(usdbrl_ret_20),
                "volatility": "UNKNOWN",
                "stress": fx_stress,
            }
        },
        "commodities": {
            "brent": {
                "last": None,
                "trend": _trend_from_return(brent_ret_20),
                "volatility": "UNKNOWN",
                "stress": brent_stress,
            },
            "iron_ore": {"last": None, "trend": "UNKNOWN", "stress": "UNKNOWN"},
            "soybean": {"last": None, "trend": "UNKNOWN", "stress": "UNKNOWN"},
            "corn": {"last": None, "trend": "UNKNOWN", "stress": "UNKNOWN"},
            "coffee": {"last": None, "trend": "UNKNOWN", "stress": "UNKNOWN"},
        },
        "equity_indices": {
            "ibov": {
                "trend": market_trend,
                "volatility": market_volatility if market_volatility != "UNKNOWN" else _volatility_bucket(ibov_vol_20),
                "breadth": "UNKNOWN",
            },
            "small": {},
            "ifnc": {},
            "imat": {},
            "icon": {},
            "iee": {},
        },
        "sector_context": _sector_context(
            drivers=thresholds.get("sector_drivers", {}),
            fx_stress=fx_stress,
            brent_stress=brent_stress,
            fiscal_risk=manual["fiscal_risk"],
        ),
        "corporate_calendar": {
            "source": "UNKNOWN",
            "events_next_7d": [],
            "events_next_30d": [],
            "earnings_next_7d": [],
            "earnings_next_30d": [],
            "dividends_next_30d": [],
        },
        "events": events,
        "regime_summary": {
            "market_regime": regime,
            "market_trend": market_trend,
            "market_volatility": market_volatility,
            "context_score": score,
            "context_quality": quality,
            "main_drivers": drivers,
            "main_risks": risks,
        },
        "headline_tags": headline_tags,
        "market_trend": market_trend,
        "market_volatility": market_volatility,
        "notes": notes,
        "source": str(auto_context.get("source", "context_consolidator")),
        "metrics": metrics,
    }


def write_market_context(
    *,
    auto_context: dict[str, Any],
    output: str | Path,
    thresholds_path: str | Path = "config/market_context_thresholds.json",
    config_path: str | Path = "config/market_context.json",
    manual_context_path: str | Path | None = None,
    previous_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = load_market_context_config(config_path)
    manual_path = manual_context_path
    if manual_path is None:
        manual_path = config.get("manual_context", "")
    payload = build_market_context(
        auto_context=auto_context,
        thresholds=load_market_context_thresholds(thresholds_path),
        config=config,
        manual_context_path=manual_path,
        previous_context=previous_context,
    )
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    payload["output"] = str(destination)
    return payload


def upgrade_legacy_market_context(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") == MARKET_CONTEXT_SCHEMA:
        return payload
    return build_market_context(
        auto_context={
            "headline_tags": payload.get("headline_tags", []),
            "market_trend": payload.get("market_trend", "UNKNOWN"),
            "market_volatility": payload.get("market_volatility", "UNKNOWN"),
            "notes": payload.get("notes", ""),
            "source": payload.get("source", "legacy_context"),
            "metrics": payload.get("metrics", {}),
        },
        previous_context=payload,
    )
