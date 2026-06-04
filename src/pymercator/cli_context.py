from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pymercator.market_context import (
    list_market_context_presets,
    load_market_context,
    load_market_context_preset,
    validate_market_context,
    write_market_context_template,
)
from pymercator.market_context_auto import write_auto_market_context
from pymercator.market_context_auto import calibrate_market_context_thresholds
from pymercator.market_context_consolidator import load_market_context_config
from pymercator.manifest import write_json
from pymercator.market_context_sources import (
    collect_market_context_sources,
    diagnostics_from_context,
    ordered_diagnostics,
    read_json_file,
    render_source_diagnostics,
)


def _split_tags(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def resolve_market_context_args(args: Any) -> dict[str, Any]:
    context: dict[str, Any] = {}
    context_source = "default"
    context_file = ""
    context_preset = ""

    if getattr(args, "context_preset", ""):
        context_preset = args.context_preset
        context = load_market_context_preset(context_preset)
        context_source = "preset"

    if getattr(args, "context", ""):
        context_file = args.context
        context = load_market_context(context_file)
        context_source = "file"

    cli_tags = _split_tags(getattr(args, "headline_tags", ""))

    if cli_tags:
        context_source = "cli"

    headline_tags = cli_tags or context.get("headline_tags", [])

    market_trend = getattr(args, "market_trend", "CHOPPY")
    if context and market_trend == "CHOPPY":
        market_trend = context.get("market_trend", market_trend)

    market_volatility = getattr(args, "market_volatility", "NORMAL")
    if context and market_volatility == "NORMAL":
        market_volatility = context.get(
            "market_volatility",
            market_volatility,
        )

    context_snapshot = dict(context)
    context_snapshot.update(
        {
            "headline_tags": headline_tags,
            "market_trend": market_trend,
            "market_volatility": market_volatility,
            "context_source": context_source,
            "context_file": context_file,
            "context_preset": context_preset,
        }
    )

    return {
        "headline_tags": headline_tags,
        "market_trend": market_trend,
        "market_volatility": market_volatility,
        "context_source": context_source,
        "context_file": context_file,
        "context_preset": context_preset,
        "context_notes": context.get("notes", ""),
        "context_snapshot": context_snapshot,
    }


def _context_file_payload(path: str | Path) -> dict[str, Any]:
    payload = read_json_file(path)
    if not payload:
        raise FileNotFoundError(f"market context not found or invalid: {path}")
    return payload


def _render_context_show(payload: dict[str, Any], *, path: str | Path) -> str:
    regime = payload.get("regime_summary", {})
    if not isinstance(regime, dict):
        regime = {}
    diagnostics = diagnostics_from_context(payload)
    lines = [
        "CONTEXT SHOW",
        "-" * 80,
        f"{'file':<18} {path}",
        f"{'schema':<18} {payload.get('schema_version', '-')}",
        f"{'generated_at':<18} {payload.get('generated_at', '-')}",
        f"{'regime':<18} {regime.get('market_regime', '-')}",
        f"{'trend':<18} {regime.get('market_trend', payload.get('market_trend', '-'))}",
        f"{'volatility':<18} {regime.get('market_volatility', payload.get('market_volatility', '-'))}",
        f"{'context_score':<18} {regime.get('context_score', '-')}",
        "",
        render_source_diagnostics(diagnostics),
    ]
    return "\n".join(lines)


def _refresh_context_sources(args: Any) -> dict[str, Any]:
    path = Path(args.file)
    payload = read_json_file(path)
    existing = diagnostics_from_context(payload) if payload else {}
    config = load_market_context_config(getattr(args, "config", "config/market_context.json"))
    source = str(getattr(args, "source", "") or "").strip().lower()
    if source and source not in {"bcb", "b3", "cvm"}:
        raise ValueError("--source must be one of BCB, B3 or CVM")
    sources = ["bcb", "b3", "cvm"] if getattr(args, "all", False) or not source else [source]
    refreshed, source_data = collect_market_context_sources(
        config=config,
        sources=sources,
        timeout=int(getattr(args, "timeout", 10) or 10),
    )
    diagnostics = {**existing, **refreshed}
    if not payload:
        payload = {
            "schema_version": "market_context.v2",
            "generated_at": "",
            "regime_summary": {},
            "context_sources": {},
        }
    payload["source_diagnostics"] = diagnostics
    context_sources = payload.get("context_sources", {})
    if not isinstance(context_sources, dict):
        context_sources = {}
    for key, diagnostic in diagnostics.items():
        if key == "market":
            context_sources["market_data"] = diagnostic.get("status", "FAIL")
        else:
            context_sources[key] = diagnostic.get("status", "FAIL")
    payload["context_sources"] = context_sources
    if source_data:
        from pymercator.market_context_sources import merge_source_data

        merge_source_data(payload, source_data)
    write_json(path, payload)
    return {
        "command": "context_refresh",
        "file": str(path),
        "sources": sources,
        "source_diagnostics": diagnostics,
    }


def run_context_command(args: Any) -> int:
    if args.context_command == "auto":
        payload = write_auto_market_context(
            indices_dir=args.indices_dir,
            output=args.output,
            thresholds_path=getattr(args, "thresholds", "config/market_context_thresholds.json"),
        )

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR MARKET CONTEXT AUTO")
            print("-" * 100)
            print(f"{'INDICES DIR':<20} {payload['indices_dir']}")
            print(f"{'OUTPUT':<20} {payload['output']}")
            print(f"{'HEADLINE TAGS':<20} {', '.join(payload['headline_tags']) or '-'}")
            print(f"{'MARKET TREND':<20} {payload['market_trend']}")
            print(f"{'VOLATILITY':<20} {payload['market_volatility']}")
            print(f"{'NOTES':<20} {payload['notes'] or '-'}")
            print("")
            print("METRICS")
            print("-" * 100)
            for key, value in payload["metrics"].items():
                print(f"{key:<42} {value}")

        return 0

    if args.context_command == "calibrate":
        payload = calibrate_market_context_thresholds(
            indices_dir=args.indices_dir,
            output=getattr(args, "output", ""),
        )

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR MARKET CONTEXT CALIBRATION")
            print("-" * 100)
            print(f"{'INDICES DIR':<20} {payload['indices_dir']}")
            print(f"{'OUTPUT':<20} {payload.get('output', '-')}")
            print("")
            print("THRESHOLDS")
            print("-" * 100)
            for key, value in payload["thresholds"].items():
                print(f"{key:<42} {float(value):>7.2f}")

        return 0

    if args.context_command == "template":
        write_market_context_template(args.output)
        print(f"Market context template written to: {args.output}")
        return 0

    if args.context_command == "presets":
        payload = list_market_context_presets()

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR MARKET CONTEXT PRESETS")
            print("-" * 100)

            for name, context in payload.items():
                tags = ", ".join(context["headline_tags"]) or "-"
                print(
                    f"{name:<16} "
                    f"trend={context['market_trend']:<7} "
                    f"vol={context['market_volatility']:<7} "
                    f"tags={tags}"
                )

        return 0

    if args.context_command == "check":
        payload = validate_market_context(args.file)

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR MARKET CONTEXT CHECK")
            print("-" * 100)
            print(f"{'FILE':<20} {payload['path']}")
            print(f"{'VALID':<20} {payload['valid']}")

            context = payload.get("context", {})
            if context:
                print(f"{'HEADLINE TAGS':<20} {', '.join(context['headline_tags']) or '-'}")
                print(f"{'MARKET TREND':<20} {context['market_trend']}")
                print(f"{'VOLATILITY':<20} {context['market_volatility']}")
                print(f"{'NOTES':<20} {context['notes']}")

            if payload["errors"]:
                print("")
                print("ERRORS")
                print("-" * 100)
                for error in payload["errors"]:
                    print(f"- {error}")

        return 0 if payload["valid"] else 1

    if args.context_command == "sources":
        payload = _context_file_payload(args.file)
        diagnostics = diagnostics_from_context(payload)

        if getattr(args, "json", False):
            print(json.dumps(ordered_diagnostics(diagnostics), ensure_ascii=False, indent=2))
        else:
            print(render_source_diagnostics(diagnostics))

        return 0

    if args.context_command == "show":
        payload = _context_file_payload(args.file)

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_render_context_show(payload, path=args.file))

        return 0

    if args.context_command == "refresh":
        payload = _refresh_context_sources(args)

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_source_diagnostics(payload["source_diagnostics"]))

        return 0

    raise ValueError(f"Unknown context command: {args.context_command}")
