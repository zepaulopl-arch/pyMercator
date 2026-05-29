from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_INDEX_FIELDS = (
    "name",
    "symbol",
    "provider",
    "category",
)


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "sim", "y"}

    return bool(value)


def normalize_index_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(record.get("name", "")).strip(),
        "symbol": str(record.get("symbol", "")).strip(),
        "provider": str(record.get("provider", "yfinance")).strip() or "yfinance",
        "category": str(record.get("category", "market")).strip() or "market",
        "description": str(record.get("description", "")).strip(),
        "required": _as_bool(record.get("required"), True),
        "enabled": _as_bool(record.get("enabled"), True),
    }


def read_indices_catalog(path: str | Path) -> dict[str, Any]:
    catalog_path = Path(path)

    if not catalog_path.exists():
        raise FileNotFoundError(f"Indices catalog not found: {catalog_path}")

    payload = json.loads(catalog_path.read_text(encoding="utf-8-sig"))

    if isinstance(payload, list):
        indices = payload
    else:
        indices = payload.get("indices", [])

    return {
        "path": str(catalog_path),
        "indices": [normalize_index_record(item) for item in indices],
    }


def validate_indices_catalog(path: str | Path) -> dict[str, Any]:
    try:
        payload = read_indices_catalog(path)
    except Exception as exc:
        return {
            "path": str(path),
            "valid": False,
            "count": 0,
            "errors": [str(exc)],
            "indices": [],
        }

    errors: list[str] = []
    seen_symbols: set[str] = set()

    for index, item in enumerate(payload["indices"], start=1):
        for field in REQUIRED_INDEX_FIELDS:
            if not item.get(field):
                errors.append(f"row {index}: missing {field}")

        symbol = item.get("symbol", "")
        if symbol in seen_symbols:
            errors.append(f"row {index}: duplicated symbol {symbol}")
        elif symbol:
            seen_symbols.add(symbol)

    return {
        "path": payload["path"],
        "valid": not errors,
        "count": len(payload["indices"]),
        "errors": errors,
        "indices": payload["indices"],
    }


def write_indices_catalog(
    *,
    output: str | Path,
    indices: list[dict[str, Any]],
) -> dict[str, Any]:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    normalized = [normalize_index_record(item) for item in indices]
    normalized.sort(key=lambda item: (item["category"], item["name"], item["symbol"]))

    payload = {
        "indices": normalized,
    }

    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    validation = validate_indices_catalog(output_path)

    return {
        "output": str(output_path),
        "count": validation["count"],
        "valid": validation["valid"],
        "errors": validation["errors"],
        "indices": normalized,
    }


def render_indices_catalog(payload: dict[str, Any]) -> str:
    line = "-" * 100
    lines = [
        "PYMERCATOR INDICES CATALOG",
        line,
        f"{'FILE':<20} {payload['path']}",
        f"{'VALID':<20} {payload['valid']}",
        f"{'INDICES':<20} {payload['count']}",
        "",
        "INDICES",
        line,
    ]

    if not payload["indices"]:
        lines.append("-")
        return "\n".join(lines)

    for item in payload["indices"]:
        required = "REQ" if item.get("required", True) else "OPT"
        enabled = "ON" if item.get("enabled", True) else "OFF"

        lines.append(
            f"{item['name']:<28} "
            f"{item['symbol']:<14} "
            f"{item['provider']:<10} "
            f"{item['category']:<16} "
            f"{required:<4} "
            f"{enabled:<3} "
            f"{item['description'] or '-'}"
        )

    if payload["errors"]:
        lines.append("")
        lines.append("ERRORS")
        lines.append(line)
        for error in payload["errors"]:
            lines.append(f"- {error}")

    return "\n".join(lines)
