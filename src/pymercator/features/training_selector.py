from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from .groups import is_excluded_column, is_duplicate_alias, canonical_name


DEFAULT_CANONICAL_PATH = Path("storage/features/latest_canonical_features.json")


def load_canonical_feature_names(path: str | Path | None = None) -> list[str]:
    p = Path(path) if path else DEFAULT_CANONICAL_PATH

    if not p.exists():
        return []

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []

    features = data.get("features", [])
    names = []

    for item in features:
        if isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))

    return names


def raw_feature_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if not is_excluded_column(c)]


def canonical_feature_columns(
    df: pd.DataFrame,
    canonical_path: str | Path | None = None,
    allow_missing: bool = True,
) -> list[str]:
    wanted = load_canonical_feature_names(canonical_path)

    if wanted:
        cols = [c for c in wanted if c in df.columns]

        if cols or allow_missing:
            return cols

    # Fallback: remove aliases conhecidos sem depender do JSON.
    cols = []
    seen = set()

    for c in raw_feature_columns(df):
        if is_duplicate_alias(c):
            continue

        canon = canonical_name(c)
        if canon in seen:
            continue

        seen.add(canon)
        cols.append(c)

    return cols


def apply_canonical_feature_filter(
    df: pd.DataFrame,
    canonical_path: str | Path | None = None,
    keep_columns: Iterable[str] = ("date", "ticker"),
) -> pd.DataFrame:
    keep = [c for c in keep_columns if c in df.columns]
    features = canonical_feature_columns(df, canonical_path=canonical_path)

    targets = [c for c in df.columns if c.startswith("target_")]

    final_cols = []
    for c in keep + features + targets:
        if c in df.columns and c not in final_cols:
            final_cols.append(c)

    return df[final_cols].copy()


def describe_canonical_selection(df: pd.DataFrame, canonical_path: str | Path | None = None) -> dict:
    raw = raw_feature_columns(df)
    canonical = canonical_feature_columns(df, canonical_path=canonical_path)

    removed = [c for c in raw if c not in canonical]

    return {
        "raw_features": len(raw),
        "canonical_features": len(canonical),
        "removed_features": len(removed),
        "removed": removed,
        "canonical": canonical,
    }
