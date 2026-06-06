"""CLI adapter for Aurum Context Engine.

This adapter keeps compatibility with older/manual context files while routing
new commands through the Context Engine.

Commands:
- context update   builds market_context.v2
- context show     shows v2, or a compatibility view for old context JSON
- context explain  explains v2, or missing coverage for old context JSON
- context audit    audits v2, or old/manual context JSON
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from pymercator.context_engine.builder import build_market_context
from pymercator.context_engine.renderer import (
    render_context_audit,
    render_context_explain,
    render_context_show,
)
from pymercator.context_engine.sources import read_json_file, write_json


DEFAULT_OUTPUT = "storage/context/latest_market_context.json"


CORE_FIELDS = ("market_trend", "market_volatility", "headline_tags", "notes")
MACRO_FIELDS = (
    "inflation_target",
    "inflation_current",
    "inflation_expectation",
    "selic",
    "interest_rate_bias",
    "copom_next_meeting",
    "copom_bias",
)
COMMODITY_FIELDS = ("oil", "brent", "wti", "iron_ore", "soybean", "corn", "coffee", "sugar")
EARNINGS_FIELDS = ("earnings_calendar", "earnings_risk", "assets_with_results_soon")
GEOPOLITICAL_FIELDS = ("geopolitical_risk", "oil_war_risk", "war_risk", "sanctions_risk")
SECTOR_FIELDS = ("sector_context", "sector_bias", "sector_risk")


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--existing-context", default=DEFAULT_OUTPUT)
    parser.add_argument("--inflation-target", type=float, default=3.0)
    parser.add_argument("--copom-csv", default="data/context/copom_calendar.csv")
    parser.add_argument("--commodities-csv", default="data/context/commodities.csv")
    parser.add_argument("--earnings-csv", default="data/context/earnings_calendar.csv")
    parser.add_argument("--geopolitical-json", default="data/context/geopolitical_context.json")
    parser.add_argument("--sector-json", default="data/context/sector_context.json")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--json", action="store_true")


def build_context_engine_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pymercator context")
    subparsers = parser.add_subparsers(dest="context_engine_command", required=True)

    update = subparsers.add_parser("update")
    _add_common(update)

    show = subparsers.add_parser("show")
    show.add_argument("--context", default=DEFAULT_OUTPUT)
    show.add_argument("--json", action="store_true")
    show.add_argument("--output", default="")

    explain = subparsers.add_parser("explain")
    explain.add_argument("--context", default=DEFAULT_OUTPUT)
    explain.add_argument("--json", action="store_true")
    explain.add_argument("--output", default="")

    audit = subparsers.add_parser("audit")
    audit.add_argument("--context", default=DEFAULT_OUTPUT)
    audit.add_argument("--json", action="store_true")
    audit.add_argument("--output", default="")

    return parser


def _flatten_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, inner in value.items():
            key_text = str(key)
            keys.add(key_text)
            keys.update(_flatten_keys(inner))
    elif isinstance(value, list):
        for inner in value:
            keys.update(_flatten_keys(inner))
    return keys


def _has_any(payload: dict[str, Any], fields: tuple[str, ...]) -> bool:
    keys = {key.lower() for key in _flatten_keys(payload)}
    return any(field.lower() in keys for field in fields)


def _coverage_status(payload: dict[str, Any], fields: tuple[str, ...]) -> str:
    return "OK" if _has_any(payload, fields) else "MISSING"


def _as_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _legacy_audit_payload(raw: dict[str, Any], *, context_status: str = "OK", error: str = "") -> dict[str, Any]:
    """Build compatibility audit payload for old/manual context JSON."""
    source_status = {
        "context_file": context_status,
        "core": _coverage_status(raw, CORE_FIELDS) if context_status == "OK" else context_status,
        "macro_inflation_rates": _coverage_status(raw, MACRO_FIELDS) if context_status == "OK" else context_status,
        "copom": _coverage_status(raw, ("copom_next_meeting", "copom_bias", "copom")) if context_status == "OK" else context_status,
        "commodities": _coverage_status(raw, COMMODITY_FIELDS) if context_status == "OK" else context_status,
        "earnings": _coverage_status(raw, EARNINGS_FIELDS) if context_status == "OK" else context_status,
        "geopolitical": _coverage_status(raw, GEOPOLITICAL_FIELDS) if context_status == "OK" else context_status,
        "sector": _coverage_status(raw, SECTOR_FIELDS) if context_status == "OK" else context_status,
    }
    missing = [
        key
        for key in (
            "macro_inflation_rates",
            "copom",
            "commodities",
            "earnings",
            "geopolitical",
            "sector",
        )
        if source_status.get(key) != "OK"
    ]
    if context_status != "OK":
        status = context_status
    elif len(missing) >= 4:
        status = "WEAK"
    elif missing:
        status = "PARTIAL"
    else:
        status = "OK"

    payload: dict[str, Any] = {
        "schema_version": "aurum_context_audit.v1",
        "date": raw.get("date", ""),
        "status": status,
        "market_trend": raw.get("market_trend", raw.get("trend", "-")),
        "market_volatility": raw.get("market_volatility", raw.get("volatility", "-")),
        "context_score": raw.get("context_score", raw.get("score", "-")),
        "headline_tags": _as_tags(raw.get("headline_tags", raw.get("tags", []))),
        "notes": raw.get("notes", raw.get("summary", "")),
        "source_status": source_status,
        "source_status_overall": status,
        "missing_context": missing,
        "source_errors": {"context": error} if error else {},
    }
    return payload


def _load_context(path: str) -> tuple[dict[str, Any], int]:
    result = read_json_file(path)
    if result.status != "OK":
        return _legacy_audit_payload({}, context_status=result.status, error=result.error), 1

    raw = result.data if isinstance(result.data, dict) else {}
    if raw.get("schema_version") == "market_context.v2":
        return raw, 0
    return _legacy_audit_payload(raw), 0


def _kv(label: str, value: Any) -> str:
    return f"{label:<24} {value}"


def _render_legacy_show(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "AURUM CONTEXT",
            "-" * 80,
            _kv("status", payload.get("status", "-")),
            _kv("market_trend", payload.get("market_trend", "-")),
            _kv("market_volatility", payload.get("market_volatility", "-")),
            _kv("context_score", payload.get("context_score", "-")),
            _kv("headline_tags", ",".join(payload.get("headline_tags", [])) or "-"),
            _kv("source_status", payload.get("source_status_overall", "-")),
        ]
    )


def _render_legacy_audit(payload: dict[str, Any]) -> str:
    lines = [
        "AURUM CONTEXT AUDIT",
        "-" * 80,
        _kv("schema_version", payload.get("schema_version", "-")),
        _kv("status", payload.get("status", "-")),
        _kv("source_status", payload.get("source_status_overall", "-")),
        "",
        "SOURCE STATUS",
        "-" * 80,
    ]
    for key, value in payload.get("source_status", {}).items():
        lines.append(_kv(key, value))
    missing = payload.get("missing_context", [])
    lines.extend(["", "MISSING COVERAGE", "-" * 80])
    lines.append(", ".join(missing) if missing else "-")
    return "\n".join(lines)


def _render_legacy_explain(payload: dict[str, Any]) -> str:
    missing = payload.get("missing_context", [])
    lines = [
        "AURUM CONTEXT EXPLAIN",
        "-" * 80,
        (
            f"Market snapshot: trend={payload.get('market_trend', '-')}, "
            f"volatility={payload.get('market_volatility', '-')}, "
            f"score={payload.get('context_score', '-')}."
        ),
    ]
    if missing:
        lines.append("Missing coverage: " + ", ".join(missing) + ".")
        lines.append(
            "The engine did not invent these fields. Add official/local sources "
            "or run context update with available sources."
        )
    else:
        lines.append("Context coverage is complete for the current compatibility audit.")
    return "\n".join(lines)


def _render_payload(payload: dict[str, Any], command: str) -> str:
    is_v2 = payload.get("schema_version") == "market_context.v2"
    if is_v2:
        if command == "audit":
            return render_context_audit(payload)
        if command == "explain":
            return render_context_explain(payload)
        return render_context_show(payload)

    if command == "audit":
        return _render_legacy_audit(payload)
    if command == "explain":
        return _render_legacy_explain(payload)
    return _render_legacy_show(payload)


def run_context_engine_argv(argv: list[str]) -> int:
    parser = build_context_engine_parser()
    args = parser.parse_args(argv)
    command = args.context_engine_command

    if command == "update":
        payload = build_market_context(
            output=args.output,
            existing_context_path=args.existing_context,
            use_network=not bool(args.offline),
            inflation_target=args.inflation_target,
            copom_csv=args.copom_csv,
            commodities_csv=args.commodities_csv,
            earnings_csv=args.earnings_csv,
            geopolitical_json=args.geopolitical_json,
            sector_json=args.sector_json,
            write_output=True,
        )
        code = 0
    else:
        payload, code = _load_context(getattr(args, "context", DEFAULT_OUTPUT))
        output = getattr(args, "output", "") or ""
        if output:
            write_json(output, payload)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_render_payload(payload, command))
    return code
