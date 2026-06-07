from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .audit import load_dataset, feature_columns
from .groups import canonical_name, is_duplicate_alias, classify_group, infer_source, infer_horizons


def build_canonical_feature_list(dataset: str | None = None) -> dict[str, Any]:
    path, df = load_dataset(dataset)
    cols = feature_columns(df)

    canonical = []
    aliases = []
    seen = set()

    for c in cols:
        canon = canonical_name(c)

        if is_duplicate_alias(c):
            aliases.append({
                "feature": c,
                "canonical": canon,
                "reason": "duplicate_alias",
            })
            continue

        if canon in seen:
            aliases.append({
                "feature": c,
                "canonical": canon,
                "reason": "duplicate_after_canonicalization",
            })
            continue

        seen.add(canon)
        g = classify_group(canon)

        canonical.append({
            "name": canon,
            "group": g,
            "source": infer_source(canon, g),
            "horizons": list(infer_horizons(canon)),
            "enabled": True,
        })

    result = {
        "dataset": str(path),
        "total_input_features": len(cols),
        "canonical_features": len(canonical),
        "removed_aliases": len(aliases),
        "features": canonical,
        "aliases": aliases,
    }

    Path("storage/features").mkdir(parents=True, exist_ok=True)
    Path("storage/reports").mkdir(parents=True, exist_ok=True)

    Path("storage/features/latest_canonical_features.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    Path("storage/reports/latest_canonical_features.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return result


def print_canonical(result: dict[str, Any], limit: int = 120) -> None:
    print("AURUM CANONICAL FEATURES")
    print("-" * 80)
    print(f"{'dataset':<25} {result['dataset']}")
    print(f"{'total_input_features':<25} {result['total_input_features']}")
    print(f"{'canonical_features':<25} {result['canonical_features']}")
    print(f"{'removed_aliases':<25} {result['removed_aliases']}")

    print()
    print("REMOVED ALIASES")
    print("-" * 80)

    if result["aliases"]:
        print(f"{'feature':<25} {'canonical':<25} {'reason':<25}")
        for a in result["aliases"]:
            print(f"{a['feature']:<25} {a['canonical']:<25} {a['reason']:<25}")
    else:
        print("none")

    print()
    print("CANONICAL FEATURE LIST")
    print("-" * 80)
    print(f"{'feature':<28} {'group':<13} {'source':<12} {'horizons':<14}")

    for f in result["features"][:limit]:
        hs = ",".join(f["horizons"])
        print(f"{f['name']:<28} {f['group']:<13} {f['source']:<12} {hs:<14}")


def canonical(args=None):
    dataset = getattr(args, "dataset", None) if args is not None else None
    limit = getattr(args, "limit", 120) if args is not None else 120
    result = build_canonical_feature_list(dataset)
    print_canonical(result, limit=limit)
    return None
