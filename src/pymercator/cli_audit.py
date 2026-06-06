"""CLI entry point for Aurum system audit."""

from __future__ import annotations

import argparse
import json

from pymercator.audit_system import audit_system, render_system_audit


def run_audit_command(args: argparse.Namespace) -> int:
    """Run audit subcommands."""
    command = getattr(args, "audit_command", None) or "system"
    if command != "system":
        print(f"Unknown audit command: {command}")
        return 2

    payload = audit_system(getattr(args, "root", "."))
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_system_audit(payload))

    status = payload.get("status")
    if status in {"OK", "LEGACY_FOUND", "CLI_HELP_WARNING"}:
        return 0
    return 1
