"""CLI entry point for Aurum audit commands."""

from __future__ import annotations

import argparse
import json

from pymercator.audit_system import audit_system, render_system_audit
from pymercator.function_catalog import (
    catalog_functions,
    render_function_catalog,
    write_function_catalog,
)


def _run_system(args: argparse.Namespace) -> int:
    payload = audit_system(getattr(args, "root", "."))
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_system_audit(payload))

    status = payload.get("status")
    if status in {"OK", "LEGACY_FOUND", "CLI_HELP_WARNING"}:
        return 0
    return 1


def _run_functions(args: argparse.Namespace) -> int:
    payload = catalog_functions(getattr(args, "root", "."))
    output = getattr(args, "output", "") or ""
    if output:
        write_function_catalog(payload, output)

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_function_catalog(payload))

    status = payload.get("status")
    if status in {"OK", "PARSE_WARNINGS"}:
        return 0
    return 1


def run_audit_command(args: argparse.Namespace) -> int:
    """Run audit subcommands."""
    command = getattr(args, "audit_command", None) or "system"
    if command == "system":
        return _run_system(args)
    if command == "functions":
        return _run_functions(args)
    print(f"Unknown audit command: {command}")
    return 2
