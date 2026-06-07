from __future__ import annotations

from typing import Any

from .audit import build_train_audit
from .history import read_history


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace("+", ""))
    except Exception:
        return default


def _fmt(value: Any) -> str:
    try:
        return f"{float(value):+.4f}"
    except Exception:
        return "-"


def _verdict(delta: float, is_best: bool) -> str:
    if is_best and delta > 0:
        return "BEST"
    if delta > 0.002:
        return "BETTER"
    if delta < -0.002:
        return "WORSE"
    return "FLAT"


def build_compare(limit: int = 10) -> dict[str, Any]:
    # Ensure current run is available, but do not duplicate history.
    current = build_train_audit(record=False)

    history = read_history(limit=limit)

    rows: list[dict[str, Any]] = []

    for item in history:
        rows.append({
            "run": item.get("run_id") or "-",
            "features": item.get("features_used") or "-",
            "engines": item.get("engines_used") or "-",
            "D5_edge": _to_float(item.get("D5_edge")),
            "D20_edge": _to_float(item.get("D20_edge")),
            "D60_edge": _to_float(item.get("D60_edge")),
            "global_edge": _to_float(item.get("global_edge")),
            "source": "history",
        })

    rows.append({
        "run": "current",
        "features": current.get("features_used") or "-",
        "engines": current.get("engines_used") or "-",
        "D5_edge": _to_float(current.get("D5_edge")),
        "D20_edge": _to_float(current.get("D20_edge")),
        "D60_edge": _to_float(current.get("D60_edge")),
        "global_edge": _to_float(current.get("global_edge")),
        "source": "current",
    })

    # Dedup by run keeping order.
    dedup = []
    seen = set()
    for row in rows:
        key = (row["run"], row["source"])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(row)

    rows = dedup

    if rows:
        best_global = max(float(row["global_edge"]) for row in rows)
        baseline = float(rows[0]["global_edge"])
    else:
        best_global = 0.0
        baseline = 0.0

    for row in rows:
        delta = float(row["global_edge"]) - baseline
        row["delta_vs_first"] = delta
        row["verdict"] = _verdict(delta, abs(float(row["global_edge"]) - best_global) <= 0.000001)

    return {
        "rows": rows,
        "best_run": next((r["run"] for r in rows if r.get("verdict") == "BEST"), "-"),
        "baseline_run": rows[0]["run"] if rows else "-",
    }


def print_compare(result: dict[str, Any]) -> None:
    print("AURUM TRAIN COMPARE")
    print("-" * 80)

    rows = result.get("rows") or []

    if not rows:
        print("none")
        return

    print(
        f"{'run':<18} "
        f"{'features':>8} "
        f"{'engines':>7} "
        f"{'D5_edge':>9} "
        f"{'D20_edge':>9} "
        f"{'D60_edge':>9} "
        f"{'global_edge':>12} "
        f"{'verdict':<10}"
    )

    for row in rows:
        print(
            f"{str(row.get('run', '-')):<18} "
            f"{str(row.get('features', '-')):>8} "
            f"{str(row.get('engines', '-')):>7} "
            f"{_fmt(row.get('D5_edge')):>9} "
            f"{_fmt(row.get('D20_edge')):>9} "
            f"{_fmt(row.get('D60_edge')):>9} "
            f"{_fmt(row.get('global_edge')):>12} "
            f"{row.get('verdict', '-'):<10}"
        )

    print()
    print(f"{'baseline_run':<18} {result.get('baseline_run') or '-'}")
    print(f"{'best_run':<18} {result.get('best_run') or '-'}")
