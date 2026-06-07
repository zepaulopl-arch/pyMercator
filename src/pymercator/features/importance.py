from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .groups import classify_group, canonical_name, is_duplicate_alias


HORIZON_DATASETS = {
    "D5": Path("storage/prediction/d5/latest_dataset.csv"),
    "D20": Path("storage/prediction/d20/latest_dataset.csv"),
    "D60": Path("storage/prediction/d60/latest_dataset.csv"),
}

EXCLUDE_PREFIXES = ("target_",)
EXCLUDE_COLUMNS = {
    "date",
    "ticker",
    "sector",
    "_close",
    "close",
    "open",
    "high",
    "low",
    "volume",
}


def _target_for_horizon(h: str) -> str:
    if h == "D5":
        return "target_up_5d"
    if h == "D20":
        return "target_up_20d"
    if h == "D60":
        return "target_up_60d"
    raise ValueError(h)


def _usable_feature_columns(df: pd.DataFrame, canonical_only: bool = True) -> list[str]:
    cols = []

    for c in df.columns:
        if c in EXCLUDE_COLUMNS:
            continue
        if any(c.startswith(p) for p in EXCLUDE_PREFIXES):
            continue

        if canonical_only and is_duplicate_alias(c):
            continue

        cols.append(c)

    return cols


def _as_numeric_series(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce")

    return s.astype("category").cat.codes.replace(-1, pd.NA).astype("float64")


def _rank_dataset(horizon: str, path: Path, canonical_only: bool = True) -> list[dict[str, Any]]:
    target = _target_for_horizon(horizon)
    df = pd.read_csv(path)

    if target not in df.columns:
        return []

    y = pd.to_numeric(df[target], errors="coerce")
    cols = _usable_feature_columns(df, canonical_only=canonical_only)

    rows = []

    for c in cols:
        try:
            x = _as_numeric_series(df[c])
            tmp = pd.concat([x.rename("x"), y.rename("y")], axis=1).dropna()

            if len(tmp) < 20:
                continue

            if tmp["x"].nunique(dropna=True) <= 1:
                score = 0.0
            else:
                corr = tmp["x"].corr(tmp["y"])
                score = 0.0 if pd.isna(corr) else abs(float(corr))

            feature_name = canonical_name(c) if canonical_only else c

            rows.append({
                "feature": feature_name,
                "raw_feature": c,
                "group": classify_group(feature_name),
                "horizon": horizon,
                "score": score,
                "method": "target_correlation_proxy",
            })
        except Exception:
            continue

    # No modo canÃ´nico, se duas colunas caÃ­rem no mesmo nome, fica a melhor.
    # No modo raw, cada coluna permanece separada.
    if canonical_only:
        best = {}

        for r in rows:
            f = r["feature"]
            if f not in best or r["score"] > best[f]["score"]:
                best[f] = r

        rows = list(best.values())

    rows.sort(key=lambda r: r["score"], reverse=True)

    for i, r in enumerate(rows, start=1):
        r["rank"] = i

    return rows


def compute_importance(canonical_only: bool = True) -> dict[str, Any]:
    by_horizon = {}

    for h, path in HORIZON_DATASETS.items():
        if path.exists():
            by_horizon[h] = _rank_dataset(h, path, canonical_only=canonical_only)
        else:
            by_horizon[h] = []

    feature_names = sorted({r["feature"] for rows in by_horizon.values() for r in rows})
    consolidated = []

    for f in feature_names:
        item = {
            "feature": f,
            "group": classify_group(f),
            "D5_rank": None,
            "D20_rank": None,
            "D60_rank": None,
            "D5_score": None,
            "D20_score": None,
            "D60_score": None,
        }

        present = 0
        good = 0

        for h in ["D5", "D20", "D60"]:
            found = next((r for r in by_horizon[h] if r["feature"] == f), None)

            if found:
                present += 1
                item[f"{h}_rank"] = found["rank"]
                item[f"{h}_score"] = found["score"]

                if found["rank"] <= 20:
                    good += 1

        if present == 3 and good >= 2:
            stability = "HIGH"
        elif present >= 2:
            stability = "MEDIUM"
        else:
            stability = "LOW"

        item["stability"] = stability
        consolidated.append(item)

    def sort_key(x):
        vals = [x.get("D5_rank"), x.get("D20_rank"), x.get("D60_rank")]
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else 999999

    consolidated.sort(key=sort_key)

    result = {
        "method": "target_correlation_proxy",
        "canonical_only": canonical_only,
        "sources": {h: str(p) for h, p in HORIZON_DATASETS.items() if p.exists()},
        "by_horizon": by_horizon,
        "features": consolidated,
    }

    Path("storage/reports").mkdir(parents=True, exist_ok=True)
    Path("storage/features").mkdir(parents=True, exist_ok=True)

    suffix = "" if canonical_only else "_raw"

    Path(f"storage/reports/latest_feature_importance{suffix}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    Path(f"storage/features/latest_feature_importance{suffix}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return result


def _fmt_rank(v):
    return "-" if v is None else str(v)


def print_importance(result: dict[str, Any], limit: int = 40) -> None:
    print("AURUM FEATURE IMPORTANCE")
    print("-" * 80)
    print(f"{'method':<25} {result['method']}")
    print(f"{'canonical_only':<25} {str(result.get('canonical_only', False)).lower()}")
    print(f"{'source':<25} storage\\prediction\\d5,d20,d60\\latest_dataset.csv")
    print(f"{'feature':<28} {'group':<13} {'D5_rank':>7} {'D20_rank':>8} {'D60_rank':>8} {'stability':<10}")

    if not result.get("features"):
        print("No feature importance rows were produced. Check D5/D20/D60 datasets and target columns.")
        return

    for item in result["features"][:limit]:
        print(
            f"{item['feature']:<28} "
            f"{item['group']:<13} "
            f"{_fmt_rank(item['D5_rank']):>7} "
            f"{_fmt_rank(item['D20_rank']):>8} "
            f"{_fmt_rank(item['D60_rank']):>8} "
            f"{item['stability']:<10}"
        )


def importance(args=None):
    limit = getattr(args, "limit", 40) if args is not None else 40
    raw = getattr(args, "raw", False) if args is not None else False

    result = compute_importance(canonical_only=not raw)
    print_importance(result, limit=limit)

    return None


feature_importance = importance
features_importance = importance
run_importance = importance


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--raw", action="store_true", help="Mostra importance sem filtro canonico")
    args = parser.parse_args(argv)
    importance(args)


if __name__ == "__main__":
    main()
