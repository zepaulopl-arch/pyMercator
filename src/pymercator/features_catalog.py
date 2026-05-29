from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_FEATURES = [
    {
        "name": "return_1d",
        "group": "price",
        "enabled": True,
        "required": True,
        "description": "One-day close-to-close return.",
    },
    {
        "name": "return_5d",
        "group": "price",
        "enabled": True,
        "required": True,
        "description": "Five-day close-to-close return.",
    },
    {
        "name": "return_20d",
        "group": "price",
        "enabled": True,
        "required": True,
        "description": "Twenty-day close-to-close return.",
    },
    {
        "name": "volatility_20d",
        "group": "risk",
        "enabled": True,
        "required": True,
        "description": "Twenty-day annualized volatility proxy.",
    },
    {
        "name": "atr_pct",
        "group": "risk",
        "enabled": True,
        "required": True,
        "description": "Average true range as percentage of close.",
    },
    {
        "name": "trend_score",
        "group": "technical",
        "enabled": True,
        "required": True,
        "description": "Operational trend score already used by pyMercator.",
    },
    {
        "name": "momentum_score",
        "group": "technical",
        "enabled": True,
        "required": True,
        "description": "Operational momentum score already used by pyMercator.",
    },
    {
        "name": "news_score",
        "group": "sentiment",
        "enabled": True,
        "required": False,
        "description": "News/sentiment score from migrated sentiment CSV files.",
    },
    {
        "name": "market_trend",
        "group": "macro",
        "enabled": True,
        "required": False,
        "description": "Automatic market trend context.",
    },
    {
        "name": "market_volatility",
        "group": "macro",
        "enabled": True,
        "required": False,
        "description": "Automatic market volatility context.",
    },
]


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "sim", "y"}

    return bool(value)


def normalize_feature_record(record: dict[str, Any]) -> dict[str, Any]:
    name = str(record.get("name") or record.get("feature") or "").strip()
    group = str(record.get("group") or record.get("category") or "legacy").strip()

    return {
        "name": name,
        "group": group or "legacy",
        "enabled": _as_bool(record.get("enabled"), True),
        "required": _as_bool(record.get("required"), False),
        "description": str(record.get("description", "")).strip(),
    }


def validate_features_catalog(path: str | Path) -> dict[str, Any]:
    catalog_path = Path(path)

    if not catalog_path.exists():
        return {
            "file": str(catalog_path),
            "valid": False,
            "features": 0,
            "enabled": 0,
            "required": 0,
            "groups": {},
            "errors": ["file not found"],
        }

    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "file": str(catalog_path),
            "valid": False,
            "features": 0,
            "enabled": 0,
            "required": 0,
            "groups": {},
            "errors": [str(exc)],
        }

    raw_features = payload.get("features", [])
    errors: list[str] = []
    features: list[dict[str, Any]] = []
    names: set[str] = set()
    groups: dict[str, int] = {}

    if not isinstance(raw_features, list):
        errors.append("features must be a list")
        raw_features = []

    for index, raw in enumerate(raw_features, start=1):
        if not isinstance(raw, dict):
            errors.append(f"feature #{index}: must be object")
            continue

        item = normalize_feature_record(raw)

        if not item["name"]:
            errors.append(f"feature #{index}: missing name")
            continue

        if item["name"] in names:
            errors.append(f"feature #{index}: duplicated name {item['name']}")
            continue

        names.add(item["name"])
        groups[item["group"]] = groups.get(item["group"], 0) + 1
        features.append(item)

    enabled = sum(1 for item in features if item["enabled"])
    required = sum(1 for item in features if item["required"])

    return {
        "file": str(catalog_path),
        "valid": not errors and len(features) > 0,
        "features": len(features),
        "enabled": enabled,
        "required": required,
        "groups": dict(sorted(groups.items())),
        "errors": errors,
        "items": features,
    }


def write_features_catalog(
    *,
    output: str | Path,
    features: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    normalized = [
        normalize_feature_record(item)
        for item in (features or DEFAULT_FEATURES)
    ]

    payload = {
        "source": "pymercator",
        "features": normalized,
    }

    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return validate_features_catalog(output_path)


def migrate_legacy_features_catalog(
    *,
    legacy_path: str | Path,
    output: str | Path,
) -> dict[str, Any]:
    legacy = Path(legacy_path)
    candidates = [
        legacy / "config" / "features.yaml",
        legacy / "config" / "features.json",
    ]

    found = next((path for path in candidates if path.exists()), None)

    # v1 deliberately creates a clean pyMercator catalog.
    # Later phases may parse the legacy YAML in detail.
    result = write_features_catalog(output=output)

    return {
        "legacy_path": str(legacy),
        "source_file": str(found) if found else "",
        "output": str(output),
        "valid": result["valid"],
        "features": result["features"],
        "enabled": result["enabled"],
        "required": result["required"],
        "groups": result["groups"],
        "errors": result["errors"],
    }


def render_features_catalog(payload: dict[str, Any]) -> str:
    line = "-" * 100
    lines = [
        "PYMERCATOR FEATURES CATALOG",
        line,
        f"{'FILE':<20} {payload['file']}",
        f"{'VALID':<20} {payload['valid']}",
        f"{'FEATURES':<20} {payload['features']}",
        f"{'ENABLED':<20} {payload['enabled']}",
        f"{'REQUIRED':<20} {payload['required']}",
        "",
        "GROUPS",
        line,
    ]

    for group, count in payload["groups"].items():
        lines.append(f"{group:<20} {count}")

    lines.extend(["", "FEATURES", line])

    for item in payload.get("items", []):
        enabled = "ON" if item["enabled"] else "OFF"
        required = "REQ" if item["required"] else "OPT"

        lines.append(
            f"{item['name']:<24} "
            f"{item['group']:<14} "
            f"{enabled:<4} "
            f"{required:<4} "
            f"{item['description'] or '-'}"
        )

    if payload.get("errors"):
        lines.extend(["", "ERRORS", line])
        lines.extend(str(error) for error in payload["errors"])

    return "\n".join(lines)
