from __future__ import annotations

import json
from typing import Any

from pymercator.market_context import (
    list_market_context_presets,
    load_market_context,
    load_market_context_preset,
    validate_market_context,
    write_market_context_template,
)
from pymercator.market_context_auto import write_auto_market_context


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


def run_context_command(args: Any) -> int:
    if args.context_command == "auto":
        payload = write_auto_market_context(
            indices_dir=args.indices_dir,
            output=args.output,
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

    raise ValueError(f"Unknown context command: {args.context_command}")
