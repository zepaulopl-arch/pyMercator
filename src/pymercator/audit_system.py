"""Aurum system audit.

This module is intentionally read-only. It scans the project layout and reports
what exists: official scripts, legacy scripts, CLI commands, feature modules,
engine modules, context modules, config files, and report artifacts.

It does not import training/model modules and does not change runtime files.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


OFFICIAL_SCRIPTS = (
    "scripts/signal.ps1",
    "scripts/review.ps1",
    "scripts/train.ps1",
    "scripts/weekend.ps1",
)

LEGACY_SCRIPTS = (
    "scripts/run_daily_signal.ps1",
    "scripts/run_daily_review.ps1",
    "scripts/run_pytrade_full_workflow.ps1",
    "scripts/run_operational_tests.ps1",
    "scripts/run_daily_operation.ps1",
    "scripts/run_weekend_full.ps1",
)

IMPORTANT_CONFIG_PATTERNS = (
    "config/*.json",
    "config/*.yaml",
    "config/*.yml",
    "storage/context/*.json",
    "data/borrow/*.csv",
    "storage/borrow/*.csv",
)

REPORT_PATTERNS = (
    "storage/reports/*.txt",
    "storage/reports/*.json",
    "runtime/*/report*.txt",
    "runtime/*/report*.json",
    "runtime/*/observation_review*.txt",
    "runtime/*/observation_review*.json",
)


def _project_root(path: str | Path = ".") -> Path:
    """Resolve a project root candidate."""
    root = Path(path).resolve()
    if root.is_file():
        root = root.parent
    return root


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _exists_map(root: Path, paths: tuple[str, ...]) -> dict[str, bool]:
    return {item: (root / item).exists() for item in paths}


def _glob_many(root: Path, patterns: tuple[str, ...]) -> list[str]:
    found: set[str] = set()
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file():
                found.add(_rel(root, path))
    return sorted(found)


def _module_files(root: Path) -> list[str]:
    source = root / "src" / "pymercator"
    if not source.exists():
        return []
    return sorted(
        _rel(root, path)
        for path in source.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _filter_modules(modules: list[str], keywords: tuple[str, ...]) -> list[str]:
    lowered_keywords = tuple(item.lower() for item in keywords)
    return [
        module
        for module in modules
        if any(keyword in module.lower() for keyword in lowered_keywords)
    ]


def _extract_commands_from_help(text: str) -> list[str]:
    """Extract argparse subcommands from pymercator --help output."""
    # Typical argparse usage has: {update,train,run,...}
    matches = re.findall(r"\{([^{}]+)\}", text)
    commands: set[str] = set()
    for match in matches:
        for item in match.split(","):
            item = item.strip()
            if item and re.fullmatch(r"[a-zA-Z0-9_-]+", item):
                commands.add(item)
    return sorted(commands)


def _cli_help_commands(root: Path) -> dict[str, Any]:
    """Try to call the current CLI help without failing the audit."""
    result: dict[str, Any] = {
        "status": "NOT_RUN",
        "commands": [],
        "error": "",
    }
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pymercator", "--help"],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - platform dependent
        result["status"] = "ERROR"
        result["error"] = str(exc)
        return result

    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    result["returncode"] = completed.returncode
    result["commands"] = _extract_commands_from_help(output)
    result["status"] = "OK" if completed.returncode == 0 else "FAIL"
    if completed.returncode != 0:
        result["error"] = output[-1000:]
    return result


def _status_from_findings(
    official_scripts: dict[str, bool],
    legacy_scripts: dict[str, bool],
    cli: dict[str, Any],
) -> str:
    missing_official = [name for name, exists in official_scripts.items() if not exists]
    found_legacy = [name for name, exists in legacy_scripts.items() if exists]
    if found_legacy:
        return "LEGACY_FOUND"
    if missing_official:
        return "MISSING_OFFICIAL_SCRIPT"
    if cli.get("status") not in {"OK", "NOT_RUN"}:
        return "CLI_HELP_WARNING"
    return "OK"


def audit_system(project_root: str | Path = ".") -> dict[str, Any]:
    """Return a read-only audit of the Aurum project."""
    root = _project_root(project_root)
    modules = _module_files(root)
    official_scripts = _exists_map(root, OFFICIAL_SCRIPTS)
    legacy_scripts = _exists_map(root, LEGACY_SCRIPTS)
    cli = _cli_help_commands(root)

    feature_modules = _filter_modules(modules, ("feature", "features"))
    engine_modules = _filter_modules(
        modules,
        ("engine", "model", "train", "prediction", "horizon"),
    )
    context_modules = _filter_modules(modules, ("context", "sentiment", "macro", "copom"))
    short_modules = _filter_modules(modules, ("short", "borrow"))
    review_modules = _filter_modules(modules, ("review", "mtm", "observation"))

    config_files = _glob_many(root, IMPORTANT_CONFIG_PATTERNS)
    report_files = _glob_many(root, REPORT_PATTERNS)

    payload: dict[str, Any] = {
        "schema_version": "aurum_system_audit.v1",
        "project_root": str(root),
        "commands": {
            "count": len(cli.get("commands", [])),
            "items": cli.get("commands", []),
            "help_status": cli.get("status"),
            "help_error": cli.get("error", ""),
        },
        "official_scripts": {
            "count": sum(1 for exists in official_scripts.values() if exists),
            "expected": list(OFFICIAL_SCRIPTS),
            "items": official_scripts,
            "missing": [name for name, exists in official_scripts.items() if not exists],
        },
        "legacy_scripts": {
            "count": sum(1 for exists in legacy_scripts.values() if exists),
            "items": legacy_scripts,
            "found": [name for name, exists in legacy_scripts.items() if exists],
        },
        "modules": {
            "total": len(modules),
            "feature_modules": feature_modules,
            "engine_modules": engine_modules,
            "context_modules": context_modules,
            "short_modules": short_modules,
            "review_modules": review_modules,
        },
        "config_files": {
            "count": len(config_files),
            "items": config_files,
        },
        "report_files": {
            "count": len(report_files),
            "items": report_files[:50],
            "truncated": len(report_files) > 50,
        },
    }
    payload["status"] = _status_from_findings(official_scripts, legacy_scripts, cli)
    return payload


def _kv(label: str, value: Any) -> str:
    return f"{label:<22} {value}"


def render_system_audit(payload: dict[str, Any]) -> str:
    """Render a compact terminal report."""
    commands = payload.get("commands", {})
    official = payload.get("official_scripts", {})
    legacy = payload.get("legacy_scripts", {})
    modules = payload.get("modules", {})
    config = payload.get("config_files", {})
    reports = payload.get("report_files", {})

    lines = [
        "AURUM SYSTEM AUDIT",
        "-" * 80,
        _kv("status", payload.get("status", "UNKNOWN")),
        _kv("project_root", payload.get("project_root", "-")),
        "",
        "COMMANDS",
        "-" * 80,
        _kv("cli_help", commands.get("help_status", "-")),
        _kv("commands", commands.get("count", 0)),
        _kv("items", ", ".join(commands.get("items", [])[:30]) or "-"),
        "",
        "SCRIPTS",
        "-" * 80,
        _kv("official_found", official.get("count", 0)),
        _kv("official_missing", ", ".join(official.get("missing", [])) or "-"),
        _kv("legacy_found", legacy.get("count", 0)),
        _kv("legacy_items", ", ".join(legacy.get("found", [])) or "-"),
        "",
        "MODULES",
        "-" * 80,
        _kv("total_modules", modules.get("total", 0)),
        _kv("feature_modules", len(modules.get("feature_modules", []))),
        _kv("engine_modules", len(modules.get("engine_modules", []))),
        _kv("context_modules", len(modules.get("context_modules", []))),
        _kv("short_modules", len(modules.get("short_modules", []))),
        _kv("review_modules", len(modules.get("review_modules", []))),
        "",
        "FILES",
        "-" * 80,
        _kv("config_files", config.get("count", 0)),
        _kv("report_files", reports.get("count", 0)),
    ]

    if commands.get("help_error"):
        lines.extend(["", "CLI HELP ERROR", "-" * 80, str(commands.get("help_error"))])

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Standalone entry point: python -m pymercator.audit_system."""
    argv = list(argv or [])
    root = argv[0] if argv else "."
    payload = audit_system(root)
    print(render_system_audit(payload))
    return 0 if payload.get("status") in {"OK", "LEGACY_FOUND", "CLI_HELP_WARNING"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
