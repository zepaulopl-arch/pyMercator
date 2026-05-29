from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

IGNORE_PATH_PARTS = {
    ".pytest_tmp_run",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "runtime",
}

IGNORE_PREFIXES = (
    "artifacts/simulations/",
)

MIGRATE_NOW_RULES = {
    "assets": (
        "config/assets/ibov_assets.yaml",
        "config/universes/ibov.yaml",
    ),
    "indices": (
        "config/indices/catalog.yaml",
    ),
    "features": (
        "config/features.yaml",
        "app/features.py",
        "app/terminal/engines/indicators.py",
    ),
    "fundamentals": (
        "app/fundamentals.py",
    ),
    "news": (
        "app/sentiment.py",
        "data/sentiment/",
    ),
}

MIGRATE_LATER_RULES = {
    "models": (
        "artifacts/models/",
    ),
    "historical": (
        "data/historical/",
    ),
    "backtests": (
        "app/evaluation_service.py",
        "app/evaluation_decision.py",
        "app/trade_plan_service.py",
        "app/domain/trade_plan.py",
    ),
}

REWRITE_RULES = {
    "features": (
        "app/feature_audit.py",
    ),
    "reports": (
        "app/terminal/screens/",
    ),
}

DISCARD_RULES = {
    "logs": (
        ".log",
        "FULL_LOG.txt",
    ),
    "patches": (
        ".patch",
    ),
}


def _path_has_ignored_part(path: str) -> bool:
    parts = set(Path(path).parts)
    return bool(parts & IGNORE_PATH_PARTS)


def _path_has_ignored_prefix(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(normalized.startswith(prefix) for prefix in IGNORE_PREFIXES)


def _matches_any(path: str, rules: dict[str, tuple[str, ...]]) -> str | None:
    normalized = path.replace("\\", "/")

    for group, patterns in rules.items():
        for pattern in patterns:
            if pattern.startswith("."):
                if normalized.endswith(pattern):
                    return group
            elif pattern in normalized:
                return group

    return None


def _classify_file(file_item: dict[str, Any]) -> dict[str, Any]:
    path = str(file_item["path"])

    if _path_has_ignored_part(path) or _path_has_ignored_prefix(path):
        decision = "IGNORAR"
        reason = "generated/test/runtime noise"
        group = "noise"

    elif group := _matches_any(path, MIGRATE_NOW_RULES):
        decision = "MIGRAR_AGORA"
        reason = f"core legacy {group} source"
        group = group

    elif group := _matches_any(path, MIGRATE_LATER_RULES):
        decision = "MIGRAR_DEPOIS"
        reason = f"useful legacy {group}, requires adapter"
        group = group

    elif group := _matches_any(path, REWRITE_RULES):
        decision = "REESCREVER_LIMPO"
        reason = f"use ideas from legacy {group}, avoid direct copy"
        group = group

    elif group := _matches_any(path, DISCARD_RULES):
        decision = "DESCARTAR"
        reason = f"legacy {group} artifact"
        group = group

    else:
        categories = file_item.get("categories", [])
        hints = file_item.get("content_hints", [])

        if "deep_learning" in hints or "sklearn" in hints or "xgboost" in hints:
            decision = "MIGRAR_DEPOIS"
            reason = "possible predictive/model code, needs review"
            group = "models"
        elif "features" in categories:
            decision = "REESCREVER_LIMPO"
            reason = "feature-related file, needs manual review"
            group = "features"
        elif "news" in categories:
            decision = "MIGRAR_DEPOIS"
            reason = "news/sentiment related file, needs adapter"
            group = "news"
        elif "fundamentals" in categories:
            decision = "MIGRAR_DEPOIS"
            reason = "fundamental data related file, needs adapter"
            group = "fundamentals"
        else:
            decision = "IGNORAR"
            reason = "not selected for migration"
            group = "uncategorized"

    return {
        "path": path,
        "extension": file_item.get("extension", ""),
        "size_bytes": file_item.get("size_bytes", 0),
        "categories": file_item.get("categories", []),
        "content_hints": file_item.get("content_hints", []),
        "decision": decision,
        "group": group,
        "reason": reason,
    }


def classify_legacy_inventory(inventory_path: str | Path) -> dict[str, Any]:
    path = Path(inventory_path)
    inventory = json.loads(path.read_text(encoding="utf-8"))

    classified = [_classify_file(file_item) for file_item in inventory["files"]]

    decision_counts = Counter(item["decision"] for item in classified)
    group_counts = Counter(item["group"] for item in classified)

    selected = {
        "migrate_now": [
            item for item in classified if item["decision"] == "MIGRAR_AGORA"
        ],
        "migrate_later": [
            item for item in classified if item["decision"] == "MIGRAR_DEPOIS"
        ],
        "rewrite_clean": [
            item for item in classified if item["decision"] == "REESCREVER_LIMPO"
        ],
        "discard": [
            item for item in classified if item["decision"] == "DESCARTAR"
        ],
        "ignore": [
            item for item in classified if item["decision"] == "IGNORAR"
        ],
    }

    return {
        "inventory_path": str(path),
        "legacy_root": inventory["root"],
        "file_count": len(classified),
        "decision_counts": dict(sorted(decision_counts.items())),
        "group_counts": dict(sorted(group_counts.items())),
        "selected": selected,
        "classified": classified,
    }


def render_legacy_classification(payload: dict[str, Any]) -> str:
    line = "-" * 118
    lines: list[str] = []

    lines.append("PYMERCATOR LEGACY CLASSIFICATION")
    lines.append(line)
    lines.append(f"{'LEGACY ROOT':<20} {payload['legacy_root']}")
    lines.append(f"{'FILES':<20} {payload['file_count']}")
    lines.append("")

    lines.append("DECISION COUNTS")
    lines.append(line)
    for decision, count in payload["decision_counts"].items():
        lines.append(f"{decision:<20} {count}")

    lines.append("")
    lines.append("GROUP COUNTS")
    lines.append(line)
    for group, count in payload["group_counts"].items():
        lines.append(f"{group:<20} {count}")

    sections = (
        ("MIGRAR AGORA", "migrate_now"),
        ("MIGRAR DEPOIS", "migrate_later"),
        ("REESCREVER LIMPO", "rewrite_clean"),
        ("DESCARTAR", "discard"),
    )

    for title, key in sections:
        lines.append("")
        lines.append(title)
        lines.append(line)

        items = payload["selected"][key]
        if not items:
            lines.append("-")
            continue

        for item in items[:80]:
            hints = ",".join(item["content_hints"]) or "-"
            categories = ",".join(item["categories"]) or "-"
            lines.append(
                f"{item['path']:<72} "
                f"{item['decision']:<16} "
                f"{item['group']:<14} "
                f"cat={categories:<24} "
                f"hints={hints}"
            )

    lines.append("")
    lines.append("RECOMMENDED NEXT MIGRATION")
    lines.append(line)
    lines.append("1. Migrate config/assets/ibov_assets.yaml and config/universes/ibov.yaml.")
    lines.append("2. Use config/indices/catalog.yaml as index-provider reference.")
    lines.append("3. Use config/features.yaml and app/features.py as feature-spec references.")
    lines.append("4. Adapt app/sentiment.py and data/sentiment/*.csv later as context inputs.")
    lines.append(
        "5. Keep artifacts/models/*.pkl for Prediction Lab, "
        "not direct production use yet."
    )

    return "\n".join(lines)


def write_legacy_classification(
    *,
    inventory_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    payload = classify_legacy_inventory(inventory_path)

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    text = render_legacy_classification(payload)

    txt_path = output / "legacy_classification.txt"
    json_path = output / "legacy_classification.json"

    txt_path.write_text(text, encoding="utf-8")
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "inventory_path": str(inventory_path),
        "output_dir": str(output),
        "txt_path": str(txt_path),
        "json_path": str(json_path),
        "file_count": payload["file_count"],
        "decision_counts": payload["decision_counts"],
        "group_counts": payload["group_counts"],
    }
