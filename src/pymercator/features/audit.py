from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .groups import classify_group, infer_source, infer_horizons, is_excluded_column


DATASET_CANDIDATES = [
    Path("storage/features/latest_feature_matrix.csv"),
    Path("storage/features/latest_feature_history.csv"),
    Path("storage/prediction/latest_prediction_dataset.csv"),
    Path("storage/prediction/d5/latest_dataset.csv"),
    Path("storage/prediction/d20/latest_dataset.csv"),
    Path("storage/prediction/d60/latest_dataset.csv"),
    Path("storage/prediction/latest_dataset.csv"),
]


def resolve_dataset(dataset: str | None = None) -> Path:
    if dataset:
        p = Path(dataset)
        if not p.exists():
            raise FileNotFoundError(f"Dataset nao encontrado: {p}")
        return p

    for p in DATASET_CANDIDATES:
        if p.exists():
            return p

    raise FileNotFoundError("Nenhum dataset de features encontrado em storage/")


def load_dataset(dataset: str | None = None) -> tuple[Path, pd.DataFrame]:
    path = resolve_dataset(dataset)
    return path, pd.read_csv(path)


def feature_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if not is_excluded_column(c)]


def _safe_missing_rate(df: pd.DataFrame, cols: list[str]) -> float:
    if not cols:
        return 0.0
    return float(df[cols].isna().mean().mean())


def _constant_features(df: pd.DataFrame, cols: list[str]) -> list[str]:
    out = []
    for c in cols:
        s = df[c]
        try:
            if s.nunique(dropna=False) <= 1:
                out.append(c)
        except Exception:
            pass
    return out


def _high_corr_pairs(df: pd.DataFrame, cols: list[str], threshold: float = 0.995) -> list[dict[str, Any]]:
    num_cols = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
    if len(num_cols) < 2:
        return []

    corr = df[num_cols].corr(numeric_only=True).abs()
    pairs = []
    seen = set()

    for a in corr.columns:
        for b in corr.columns:
            if a == b:
                continue
            key = tuple(sorted((a, b)))
            if key in seen:
                continue
            seen.add(key)
            val = corr.loc[a, b]
            if pd.notna(val) and float(val) >= threshold:
                pairs.append({
                    "feature_a": a,
                    "feature_b": b,
                    "corr": round(float(val), 6),
                })

    pairs.sort(key=lambda x: x["corr"], reverse=True)
    return pairs


def audit_dataset(dataset: str | None = None) -> dict[str, Any]:
    path, df = load_dataset(dataset)
    cols = feature_columns(df)

    specs = []
    unknown = []
    for c in cols:
        group = classify_group(c)
        if group == "unknown":
            unknown.append(c)
        specs.append({
            "name": c,
            "group": group,
            "source": infer_source(c, group),
            "horizons": list(infer_horizons(c)),
            "enabled": True,
        })

    constants = _constant_features(df, cols)
    corr_pairs = _high_corr_pairs(df, cols)

    low_quality = []
    for c in constants:
        low_quality.append({"feature": c, "group": classify_group(c), "reason": "constant"})
    for c in unknown:
        low_quality.append({"feature": c, "group": "unknown", "reason": "unknown_group"})
    for p in corr_pairs:
        low_quality.append({"feature": p["feature_a"], "group": classify_group(p["feature_a"]), "reason": "highly_correlated"})
        low_quality.append({"feature": p["feature_b"], "group": classify_group(p["feature_b"]), "reason": "highly_correlated"})

    # Dedup mantendo ordem
    dedup = []
    seen = set()
    for item in low_quality:
        key = (item["feature"], item["reason"])
        if key not in seen:
            seen.add(key)
            dedup.append(item)

    status = "OK"
    if constants or unknown or corr_pairs:
        status = "WARN"

    result = {
        "dataset": str(path),
        "rows": int(len(df)),
        "features": int(len(cols)),
        "enabled_features": int(len(cols)),
        "used_in_training": int(len(cols)),
        "excluded_columns": [c for c in df.columns if c not in cols],
        "missing_rate": _safe_missing_rate(df, cols),
        "constant_features": constants,
        "high_corr_pairs": corr_pairs,
        "unknown_group_features": unknown,
        "low_quality_features": dedup,
        "feature_specs": specs,
        "status": status,
    }

    Path("storage/features").mkdir(parents=True, exist_ok=True)
    Path("storage/reports").mkdir(parents=True, exist_ok=True)

    Path("storage/features/latest_feature_audit.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    Path("storage/reports/latest_feature_audit.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return result


def _print_kv(label: str, value: object) -> None:
    print(f"{label:<25} {value}")


def print_audit(result: dict[str, Any]) -> None:
    print("AURUM FEATURE AUDIT")
    print("-" * 80)
    _print_kv("dataset", result["dataset"])
    _print_kv("rows", result["rows"])
    _print_kv("features", result["features"])
    _print_kv("enabled_features", result["enabled_features"])
    _print_kv("used_in_training", result["used_in_training"])
    _print_kv("excluded_columns", len(result["excluded_columns"]))
    _print_kv("missing_rate", f"{result['missing_rate']:.1%}")
    _print_kv("constant_features", len(result["constant_features"]))
    _print_kv("high_corr_pairs", len(result["high_corr_pairs"]))
    _print_kv("unknown_group_features", len(result["unknown_group_features"]))
    _print_kv("status", result["status"])

    print()
    print("CONSTANT FEATURES")
    print("-" * 80)
    if result["constant_features"]:
        print(f"{'feature':<25} {'group':<12}")
        for f in result["constant_features"]:
            print(f"{f:<25} {classify_group(f):<12}")
    else:
        print("none")

    print()
    print("HIGH CORRELATION PAIRS")
    print("-" * 80)
    if result["high_corr_pairs"]:
        print(f"{'feature_a':<25} {'feature_b':<25} {'corr':<8}")
        for p in result["high_corr_pairs"][:40]:
            print(f"{p['feature_a']:<25} {p['feature_b']:<25} {p['corr']:<8}")
    else:
        print("none")

    print()
    print("EXCLUDED COLUMNS")
    print("-" * 80)
    for c in result["excluded_columns"]:
        print(c)

    print()
    print("LOW QUALITY FEATURES")
    print("-" * 80)
    if result["low_quality_features"]:
        print(f"{'feature':<25} {'group':<12} {'reason':<18}")
        for item in result["low_quality_features"][:80]:
            print(f"{item['feature']:<25} {item['group']:<12} {item['reason']:<18}")
    else:
        print("none")


def audit(args=None):
    dataset = getattr(args, "dataset", None) if args is not None else None
    result = audit_dataset(dataset)
    print_audit(result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=None)
    args = parser.parse_args(argv)
    audit(args)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# Backward compatibility for older features/cli.py imports
# ---------------------------------------------------------------------------

def audit_features(dataset: str | None = None, *args, **kwargs):
    """Compatibility wrapper expected by older CLI code."""
    if dataset is None:
        dataset = kwargs.get("dataset")
    return audit_dataset(dataset)


def build_feature_summary(dataset: str | None = None, *args, **kwargs):
    """Compatibility wrapper expected by older CLI code."""
    if dataset is None:
        dataset = kwargs.get("dataset")

    result = audit_dataset(dataset)
    specs = result.get("feature_specs", [])

    groups = {}
    for s in specs:
        g = s.get("group", "unknown")
        groups[g] = groups.get(g, 0) + 1

    return {
        "dataset": result.get("dataset"),
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
        "missing_rate": result.get("missing_rate", 0.0),
        "constant_features": len(result.get("constant_features", [])),
        "high_corr_pairs": len(result.get("high_corr_pairs", [])),
        "status": result.get("status", "UNKNOWN"),
    }

