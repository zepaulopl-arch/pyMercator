"""Renderers for Aurum Context Engine."""

from __future__ import annotations

from typing import Any


def _kv(label: str, value: Any) -> str:
    return f"{label:<24} {value}"


def render_context_show(payload: dict[str, Any]) -> str:
    inflation = payload.get("inflation", {})
    rates = payload.get("rates", {})
    copom = payload.get("copom", {})
    commodities = payload.get("commodities", {})
    earnings = payload.get("earnings", {})
    lines = [
        "AURUM CONTEXT",
        "-" * 80,
        _kv("date", payload.get("date", "-")),
        _kv("market_trend", payload.get("market_trend", "-")),
        _kv("market_volatility", payload.get("market_volatility", "-")),
        _kv("context_score", payload.get("context_score", "-")),
        _kv("inflation_bias", inflation.get("bias", "-")),
        _kv("selic_bias", rates.get("selic_bias", "-")),
        _kv("copom_risk", copom.get("risk", "-")),
        _kv("oil_risk", commodities.get("oil_risk", "-")),
        _kv("earnings_risk", earnings.get("risk", "-")),
        _kv("headline_tags", ",".join(payload.get("headline_tags", [])) or "-"),
        _kv("source_status", payload.get("source_status_overall", "-")),
    ]
    return "\n".join(lines)


def render_context_audit(payload: dict[str, Any]) -> str:
    lines = [
        "AURUM CONTEXT AUDIT",
        "-" * 80,
        _kv("schema_version", payload.get("schema_version", "-")),
        _kv("date", payload.get("date", "-")),
        _kv("source_status", payload.get("source_status_overall", "-")),
        "",
        "SOURCE STATUS",
        "-" * 80,
    ]
    for key, value in payload.get("source_status", {}).items():
        lines.append(_kv(key, value))
    errors = payload.get("source_errors", {})
    if errors:
        lines.extend(["", "SOURCE ERRORS", "-" * 80])
        for key, value in errors.items():
            lines.append(_kv(key, value))
    return "\n".join(lines)


def render_context_explain(payload: dict[str, Any]) -> str:
    inflation = payload.get("inflation", {})
    rates = payload.get("rates", {})
    copom = payload.get("copom", {})
    commodities = payload.get("commodities", {})
    earnings = payload.get("earnings", {})
    geopolitical = payload.get("geopolitical", {})

    lines = [
        "AURUM CONTEXT EXPLAIN",
        "-" * 80,
        (
            f"Market is classified as {payload.get('market_trend', '-')} with "
            f"{payload.get('market_volatility', '-')} volatility and context score "
            f"{payload.get('context_score', '-')}."
        ),
        (
            f"Inflation bias is {inflation.get('bias', 'UNKNOWN')}; "
            f"Selic bias is {rates.get('selic_bias', 'UNKNOWN')}."
        ),
        (
            f"COPOM risk is {copom.get('risk', 'UNKNOWN')}; oil risk is "
            f"{commodities.get('oil_risk', 'UNKNOWN')}; earnings risk is "
            f"{earnings.get('risk', 'UNKNOWN')}; geopolitical risk is "
            f"{geopolitical.get('risk', 'UNKNOWN')}."
        ),
        "",
        "SOURCE STATUS",
        "-" * 80,
    ]
    for key, value in payload.get("source_status", {}).items():
        lines.append(_kv(key, value))

    if payload.get("source_errors"):
        lines.extend(["", "The engine did not invent missing data. Errors/missing sources remain explicit."])
    return "\n".join(lines)
