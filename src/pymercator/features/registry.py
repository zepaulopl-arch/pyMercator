from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from .audit import load_dataset, feature_columns, audit_dataset
from .groups import classify_group, infer_source, infer_horizons


def build_feature_specs(dataset: str | None = None) -> list[dict[str, Any]]:
    path, df = load_dataset(dataset)
    cols = feature_columns(df)
    specs = []
    for c in cols:
        g = classify_group(c)
        specs.append({
            "name": c,
            "group": g,
            "source": infer_source(c, g),
            "horizon_relevance": list(infer_horizons(c)),
            "enabled": True,
            "description": f"Auto-registered feature: {c}",
        })

    Path("storage/features").mkdir(parents=True, exist_ok=True)
    Path("storage/features/latest_feature_list.json").write_text(
        json.dumps({"dataset": str(path), "features": specs}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return specs


def summarize_features(dataset: str | None = None) -> dict[str, Any]:
    audit = audit_dataset(dataset)
    specs = audit["feature_specs"]

    groups = Counter(s["group"] for s in specs)
    result = {
        "dataset": audit["dataset"],
        "total_features": len(specs),
        "enabled_features": len([s for s in specs if s.get("enabled", True)]),
        "disabled_features": len([s for s in specs if not s.get("enabled", True)]),
        "price_features": groups.get("price", 0),
        "trend_features": groups.get("trend", 0),
        "momentum_features": groups.get("momentum", 0),
        "volatility_features": groups.get("volatility", 0),
        "sector_features": groups.get("sector", 0),
        "context_features": groups.get("context", 0),
        "macro_features": groups.get("macro", 0),
        "unknown_features": groups.get("unknown", 0),
        "missing_rate": audit["missing_rate"],
        "constant_features": len(audit["constant_features"]),
        "high_corr_pairs": len(audit["high_corr_pairs"]),
        "status": audit["status"],
    }

    Path("storage/reports").mkdir(parents=True, exist_ok=True)
    Path("storage/reports/latest_feature_summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return result


def print_summary(result: dict[str, Any]) -> None:
    print("AURUM FEATURE SUMMARY")
    print("-" * 80)
    for key in [
        "total_features",
        "enabled_features",
        "disabled_features",
        "price_features",
        "trend_features",
        "momentum_features",
        "volatility_features",
        "sector_features",
        "context_features",
        "macro_features",
        "unknown_features",
    ]:
        print(f"{key:<25} {result[key]}")

    print(f"{'missing_rate':<25} {result['missing_rate']:.1%}")
    print(f"{'constant_features':<25} {result['constant_features']}")
    print(f"{'high_corr_pairs':<25} {result['high_corr_pairs']}")
    print(f"{'status':<25} {result['status']}")
    print(f"{'dataset':<25} {result['dataset']}")


def print_list(specs: list[dict[str, Any]]) -> None:
    print("AURUM FEATURE LIST")
    print("-" * 80)
    print(f"{'feature':<28} {'group':<13} {'source':<12} {'horizons':<14} {'enabled':<8}")
    for s in specs:
        horizons = ",".join(s["horizon_relevance"])
        enabled = "yes" if s.get("enabled", True) else "no"
        print(f"{s['name']:<28} {s['group']:<13} {s['source']:<12} {horizons:<14} {enabled:<8}")


def summary(args=None):
    dataset = getattr(args, "dataset", None) if args is not None else None
    result = summarize_features(dataset)
    print_summary(result)
    return result


def list_features(args=None):
    dataset = getattr(args, "dataset", None) if args is not None else None
    specs = build_feature_specs(dataset)
    print_list(specs)
    return specs


# aliases para compatibilidade com dispatchers antigos
feature_summary = summary
features_summary = summary
feature_list = list_features
features_list = list_features
run_summary = summary
run_list = list_features


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_summary = sub.add_parser("summary")
    p_summary.add_argument("--dataset", default=None)

    p_list = sub.add_parser("list")
    p_list.add_argument("--dataset", default=None)

    args = parser.parse_args(argv)

    if args.cmd == "summary":
        summary(args)
    elif args.cmd == "list":
        list_features(args)


if __name__ == "__main__":
    main()
