from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pymercator.market_context_consolidator import (
    MARKET_CONTEXT_SCHEMA,
    upgrade_legacy_market_context,
)

VALID_MARKET_TRENDS = {"UP", "DOWN", "CHOPPY", "UNKNOWN"}
VALID_MARKET_VOLATILITY = {"LOW", "NORMAL", "HIGH", "UNKNOWN"}

DEFAULT_MARKET_CONTEXT = {
    "headline_tags": [],
    "market_trend": "CHOPPY",
    "market_volatility": "NORMAL",
    "notes": "",
}


CONTEXT_PRESETS = {
    "normal": {
        "headline_tags": [],
        "market_trend": "CHOPPY",
        "market_volatility": "NORMAL",
        "notes": "dia sem evento macro relevante",
    },
    "oil_war": {
        "headline_tags": ["IRAN", "OIL", "WAR"],
        "market_trend": "CHOPPY",
        "market_volatility": "NORMAL",
        "notes": "stress geopolitico com impacto potencial em energia",
    },
    "fed_day": {
        "headline_tags": ["FED", "RATES", "USD"],
        "market_trend": "CHOPPY",
        "market_volatility": "HIGH",
        "notes": "dia de decis?o ou comunica??o relevante do Federal Reserve",
    },
    "copom_day": {
        "headline_tags": ["COPOM", "SELIC", "RATES"],
        "market_trend": "CHOPPY",
        "market_volatility": "HIGH",
        "notes": "dia de decis?o ou comunica??o relevante do Copom",
    },
    "risk_on": {
        "headline_tags": ["RISK_ON"],
        "market_trend": "UP",
        "market_volatility": "NORMAL",
        "notes": "ambiente favor?vel a risco",
    },
    "risk_off": {
        "headline_tags": ["RISK_OFF"],
        "market_trend": "DOWN",
        "market_volatility": "HIGH",
        "notes": "ambiente defensivo com avers?o a risco",
    },
    "china_stress": {
        "headline_tags": ["CHINA", "COMMODITIES", "RISK_OFF"],
        "market_trend": "CHOPPY",
        "market_volatility": "HIGH",
        "notes": "stress ligado a China e commodities",
    },
    "fiscal_stress": {
        "headline_tags": ["FISCAL", "RATES", "BRL"],
        "market_trend": "CHOPPY",
        "market_volatility": "HIGH",
        "notes": "stress fiscal/local com impacto em juros, c?mbio e bolsa",
    },
}


def _normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        return [item.strip().upper() for item in value.split(",") if item.strip()]

    if isinstance(value, list):
        return [str(item).strip().upper() for item in value if str(item).strip()]

    raise ValueError("headline_tags must be a list or comma-separated string")


def load_market_context(path: str | Path) -> dict[str, Any]:
    context_path = Path(path)

    if not context_path.exists():
        raise FileNotFoundError(f"Market context file not found: {context_path}")

    payload = json.loads(context_path.read_text(encoding="utf-8-sig"))

    if isinstance(payload, dict) and payload.get("schema_version") == MARKET_CONTEXT_SCHEMA:
        context = dict(payload)
        regime_summary = context.get("regime_summary", {})
        if isinstance(regime_summary, dict):
            context.setdefault("market_trend", regime_summary.get("market_trend", "UNKNOWN"))
            context.setdefault(
                "market_volatility",
                regime_summary.get("market_volatility", "UNKNOWN"),
            )
        events = context.get("events", {})
        manual = context.get("manual_overrides", {})
        if isinstance(events, dict):
            context.setdefault("headline_tags", events.get("headline_tags", []))
            context.setdefault("notes", events.get("manual_notes", ""))
        elif isinstance(manual, dict):
            context.setdefault("headline_tags", manual.get("headline_tags", []))
            context.setdefault("notes", manual.get("notes", ""))
    else:
        context = upgrade_legacy_market_context(dict(payload))

    context["headline_tags"] = _normalize_tags(context.get("headline_tags"))
    context["market_trend"] = str(context.get("market_trend", "CHOPPY")).upper()
    context["market_volatility"] = str(
        context.get("market_volatility", "NORMAL")
    ).upper()
    context["notes"] = str(context.get("notes", ""))

    return context


def validate_market_context(path: str | Path) -> dict[str, Any]:
    errors: list[str] = []

    try:
        context = load_market_context(path)
    except Exception as exc:
        return {
            "path": str(path),
            "valid": False,
            "errors": [str(exc)],
            "context": {},
        }

    if context["market_trend"] not in VALID_MARKET_TRENDS:
        errors.append(f"invalid market_trend: {context['market_trend']}")

    if context["market_volatility"] not in VALID_MARKET_VOLATILITY:
        errors.append(
            f"invalid market_volatility: {context['market_volatility']}"
        )

    return {
        "path": str(path),
        "valid": not errors,
        "errors": errors,
        "context": context,
    }


def write_market_context_template(path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)

    output.write_text(
        json.dumps(
            {"schema_version": "market_context.v1", **DEFAULT_MARKET_CONTEXT},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

def list_market_context_presets() -> dict[str, dict[str, Any]]:
    return dict(CONTEXT_PRESETS)


def load_market_context_preset(name: str) -> dict[str, Any]:
    preset_name = name.strip().lower()

    if preset_name not in CONTEXT_PRESETS:
        available = ", ".join(sorted(CONTEXT_PRESETS))
        raise ValueError(
            f"Unknown context preset: {name}. Available presets: {available}"
        )

    context = dict(DEFAULT_MARKET_CONTEXT)
    context.update(CONTEXT_PRESETS[preset_name])
    context["headline_tags"] = _normalize_tags(context["headline_tags"])
    context["market_trend"] = str(context["market_trend"]).upper()
    context["market_volatility"] = str(context["market_volatility"]).upper()
    context["notes"] = str(context.get("notes", ""))

    return context

