"""Aurum function catalog.

This module scans Python source files and inventories functions/classes without
importing project modules. It is read-only and safe to run before refactors.

Goal:
- discover public functions;
- group them by operational domain;
- identify probable CLI handlers, renderers, builders, loaders, savers, trainers,
  evaluators, feature functions, context functions, engine functions, and review
  functions;
- produce a compact report that guides future command-to-function refactors.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


PRIVATE_PREFIX = "_"


DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "audit": ("audit",),
    "basket": ("basket",),
    "borrow_short": ("borrow", "short", "sell"),
    "cli": ("cli", "parser", "command"),
    "context": ("context", "sentiment", "macro", "copom"),
    "data_update": ("update", "prices", "universe", "indices"),
    "execution": ("execution", "permission", "policy", "position", "actions"),
    "features": ("feature", "features", "matrix"),
    "engines_models": ("engine", "model", "prediction", "train", "horizon", "ridge"),
    "rendering": ("render", "format", "terminal", "ui", "summary"),
    "review_mtm": ("review", "mtm", "observation"),
    "storage": ("storage", "repository", "db", "save", "load"),
}


ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "builder": ("build_", "make_", "create_"),
    "checker": ("check_", "validate_", "verify_"),
    "cli_runner": ("run_", "_run_"),
    "converter": ("to_", "from_", "parse_", "normalize_"),
    "loader": ("load_", "read_", "fetch_"),
    "renderer": ("render_", "format_"),
    "saver": ("save_", "write_", "persist_"),
    "trainer": ("train_", "fit_", "evaluate_", "benchmark_"),
}


def _project_root(path: str | Path = ".") -> Path:
    return Path(path).resolve()


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _safe_parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except Exception:
        return None


def _iter_python_files(root: Path) -> list[Path]:
    source = root / "src" / "pymercator"
    if not source.exists():
        return []
    return sorted(
        path
        for path in source.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _classify_domain(module: str, name: str) -> str:
    text = f"{module} {name}".lower()
    scores: dict[str, int] = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        scores[domain] = sum(1 for keyword in keywords if keyword in text)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "misc"


def _classify_roles(name: str) -> list[str]:
    lowered = name.lower()
    roles: list[str] = []
    for role, prefixes in ROLE_KEYWORDS.items():
        if any(lowered.startswith(prefix) for prefix in prefixes):
            roles.append(role)
    return roles or ["function"]


def _arg_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    args: list[str] = []
    for arg in list(node.args.posonlyargs) + list(node.args.args):
        args.append(arg.arg)
    if node.args.vararg:
        args.append("*" + node.args.vararg.arg)
    for arg in node.args.kwonlyargs:
        args.append(arg.arg)
    if node.args.kwarg:
        args.append("**" + node.args.kwarg.arg)
    return args


def _decorator_names(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> list[str]:
    names: list[str] = []
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name):
            names.append(decorator.id)
        elif isinstance(decorator, ast.Attribute):
            names.append(decorator.attr)
        elif isinstance(decorator, ast.Call):
            func = decorator.func
            if isinstance(func, ast.Name):
                names.append(func.id)
            elif isinstance(func, ast.Attribute):
                names.append(func.attr)
    return names


def _function_item(
    root: Path,
    path: Path,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    class_name: str | None = None,
) -> dict[str, Any]:
    module = _rel(root, path)
    name = node.name
    qualified = f"{class_name}.{name}" if class_name else name
    is_private = name.startswith(PRIVATE_PREFIX)
    domain = _classify_domain(module, qualified)
    return {
        "module": module,
        "name": name,
        "qualified_name": qualified,
        "class": class_name or "",
        "line": int(getattr(node, "lineno", 0) or 0),
        "end_line": int(getattr(node, "end_lineno", 0) or 0),
        "args": _arg_names(node),
        "decorators": _decorator_names(node),
        "is_private": is_private,
        "is_async": isinstance(node, ast.AsyncFunctionDef),
        "domain": domain,
        "roles": _classify_roles(name),
        "doc": ast.get_docstring(node) or "",
    }


def _class_item(root: Path, path: Path, node: ast.ClassDef) -> dict[str, Any]:
    module = _rel(root, path)
    name = node.name
    return {
        "module": module,
        "name": name,
        "line": int(getattr(node, "lineno", 0) or 0),
        "end_line": int(getattr(node, "end_lineno", 0) or 0),
        "decorators": _decorator_names(node),
        "domain": _classify_domain(module, name),
        "doc": ast.get_docstring(node) or "",
    }


def catalog_functions(project_root: str | Path = ".") -> dict[str, Any]:
    """Return a function/class catalog for src/pymercator."""
    root = _project_root(project_root)
    python_files = _iter_python_files(root)
    functions: list[dict[str, Any]] = []
    classes: list[dict[str, Any]] = []
    parse_errors: list[dict[str, str]] = []

    for path in python_files:
        parsed = _safe_parse(path)
        if parsed is None:
            parse_errors.append({"module": _rel(root, path), "error": "parse failed"})
            continue

        for node in parsed.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(_function_item(root, path, node))
            elif isinstance(node, ast.ClassDef):
                classes.append(_class_item(root, path, node))
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        functions.append(
                            _function_item(root, path, child, class_name=node.name)
                        )

    domains: dict[str, int] = {}
    roles: dict[str, int] = {}
    modules: dict[str, int] = {}

    for item in functions:
        domains[item["domain"]] = domains.get(item["domain"], 0) + 1
        modules[item["module"]] = modules.get(item["module"], 0) + 1
        for role in item["roles"]:
            roles[role] = roles.get(role, 0) + 1

    public_functions = [item for item in functions if not item["is_private"]]
    private_functions = [item for item in functions if item["is_private"]]

    payload: dict[str, Any] = {
        "schema_version": "aurum_function_catalog.v1",
        "project_root": str(root),
        "summary": {
            "modules_scanned": len(python_files),
            "functions_total": len(functions),
            "functions_public": len(public_functions),
            "functions_private": len(private_functions),
            "classes_total": len(classes),
            "parse_errors": len(parse_errors),
        },
        "domains": dict(sorted(domains.items())),
        "roles": dict(sorted(roles.items())),
        "top_modules": [
            {"module": module, "functions": count}
            for module, count in sorted(
                modules.items(),
                key=lambda item: (-item[1], item[0]),
            )[:25]
        ],
        "functions": sorted(
            functions,
            key=lambda item: (item["module"], item["line"], item["qualified_name"]),
        ),
        "classes": sorted(classes, key=lambda item: (item["module"], item["line"])),
        "parse_errors": parse_errors,
    }
    payload["status"] = "OK" if not parse_errors else "PARSE_WARNINGS"
    return payload


def _kv(label: str, value: Any) -> str:
    return f"{label:<24} {value}"


def _counter_lines(counter: dict[str, int]) -> list[str]:
    lines: list[str] = []
    for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0])):
        lines.append(_kv(key, count))
    return lines


def _module_lines(top_modules: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in top_modules[:15]:
        lines.append(f"{item['functions']:>4}  {item['module']}")
    return lines


def render_function_catalog(payload: dict[str, Any]) -> str:
    """Render a compact function catalog."""
    summary = payload.get("summary", {})
    lines = [
        "AURUM FUNCTION CATALOG",
        "-" * 80,
        _kv("status", payload.get("status", "UNKNOWN")),
        _kv("project_root", payload.get("project_root", "-")),
        "",
        "SUMMARY",
        "-" * 80,
        _kv("modules_scanned", summary.get("modules_scanned", 0)),
        _kv("functions_total", summary.get("functions_total", 0)),
        _kv("functions_public", summary.get("functions_public", 0)),
        _kv("functions_private", summary.get("functions_private", 0)),
        _kv("classes_total", summary.get("classes_total", 0)),
        _kv("parse_errors", summary.get("parse_errors", 0)),
        "",
        "DOMAINS",
        "-" * 80,
    ]
    lines.extend(_counter_lines(payload.get("domains", {})) or ["-"])
    lines.extend(["", "ROLES", "-" * 80])
    lines.extend(_counter_lines(payload.get("roles", {})) or ["-"])
    lines.extend(["", "TOP MODULES BY FUNCTION COUNT", "-" * 80])
    lines.extend(_module_lines(payload.get("top_modules", [])) or ["-"])
    return "\n".join(lines)


def write_function_catalog(
    payload: dict[str, Any],
    output: str | Path = "storage/audit/latest_function_catalog.json",
) -> Path:
    """Write the full catalog to JSON."""
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m pymercator.function_catalog")
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)

    payload = catalog_functions(args.root)
    if args.output:
        write_function_catalog(payload, args.output)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_function_catalog(payload))
    return 0 if payload.get("status") in {"OK", "PARSE_WARNINGS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())


