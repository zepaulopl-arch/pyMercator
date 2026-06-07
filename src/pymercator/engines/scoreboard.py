from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .registry import ENGINE_REGISTRY


EVALUATION_CANDIDATES = [
    Path("storage/prediction/latest_multi_horizon_evaluation.json"),
    Path("storage/prediction/latest_evaluation.json"),
    Path("storage/reports/latest_daily_report.json"),
]

HORIZON_FILES = {
    "D5": Path("storage/prediction/d5/latest_evaluation.json"),
    "D20": Path("storage/prediction/d20/latest_evaluation.json"),
    "D60": Path("storage/prediction/d60/latest_evaluation.json"),
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


def _horizon_label(value: Any) -> str | None:
    raw = str(value).upper().strip()

    if raw in {"D5", "5"}:
        return "D5"
    if raw in {"D20", "20"}:
        return "D20"
    if raw in {"D60", "60"}:
        return "D60"

    if raw.endswith("D"):
        number = raw[:-1]
        if number in {"5", "20", "60"}:
            return f"D{number}"

    return None


def _accuracy(metrics: Any) -> float | None:
    if not isinstance(metrics, dict):
        return None

    for key in ("accuracy", "acc", "ACC"):
        if key in metrics:
            try:
                return float(metrics[key])
            except Exception:
                return None

    return None


def _collect_horizon_payloads(obj: Any, found: dict[str, dict[str, Any]]) -> None:
    if isinstance(obj, dict):
        horizon = None

        for key in ("horizon", "HZ", "hz"):
            if key in obj:
                horizon = _horizon_label(obj.get(key))
                break

        if horizon and (
            isinstance(obj.get("base_metrics"), dict)
            or isinstance(obj.get("ensemble_metrics"), dict)
            or isinstance(obj.get("models"), dict)
        ):
            found.setdefault(horizon, obj)

        for key, value in obj.items():
            key_horizon = _horizon_label(key)
            if key_horizon and isinstance(value, dict):
                if (
                    isinstance(value.get("base_metrics"), dict)
                    or isinstance(value.get("ensemble_metrics"), dict)
                    or isinstance(value.get("models"), dict)
                ):
                    found.setdefault(key_horizon, value)

            _collect_horizon_payloads(value, found)

    elif isinstance(obj, list):
        for item in obj:
            _collect_horizon_payloads(item, found)


def load_horizon_payloads() -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}

    for horizon, path in HORIZON_FILES.items():
        data = _read_json(path)
        if data:
            found[horizon] = data

    for path in EVALUATION_CANDIDATES:
        data = _read_json(path)
        if data:
            _collect_horizon_payloads(data, found)

    return found


def _engine_accuracy_from_payload(payload: dict[str, Any], engine: str) -> float | None:
    base_metrics = payload.get("base_metrics")
    if isinstance(base_metrics, dict):
        metrics = base_metrics.get(engine)
        acc = _accuracy(metrics)
        if acc is not None:
            return acc

    models = payload.get("models")
    if isinstance(models, dict):
        lookup_names = [engine]
        if engine == "ridge_meta":
            lookup_names.extend(["ridge_ensemble", "ridge", "meta_ridge"])

        for name in lookup_names:
            acc = _accuracy(models.get(name))
            if acc is not None:
                return acc

    if engine == "ridge_meta":
        for key in ("ensemble_metrics", "ridge_metrics", "meta_metrics"):
            acc = _accuracy(payload.get(key))
            if acc is not None:
                return acc

    return None


def build_scoreboard() -> dict[str, Any]:
    horizons = load_horizon_payloads()

    rows: list[dict[str, Any]] = []

    for spec in ENGINE_REGISTRY:
        row: dict[str, Any] = {
            "engine": spec.name,
            "backend": spec.backend,
            "role": spec.role,
            "enabled": spec.enabled,
            "D5_acc": None,
            "D20_acc": None,
            "D60_acc": None,
            "edge": None,
            "status": "MISSING",
            "read": "not_found",
        }

        accs = []

        for horizon in ("D5", "D20", "D60"):
            payload = horizons.get(horizon, {})
            acc = _engine_accuracy_from_payload(payload, spec.name)
            row[f"{horizon}_acc"] = acc
            if acc is not None:
                accs.append(acc)

        if accs:
            avg_acc = sum(accs) / len(accs)
            edge = avg_acc - 0.5
            row["edge"] = edge
            row["read"] = "ran"

            if edge < 0:
                row["status"] = "BAD"
            elif edge < 0.005:
                row["status"] = "WEAK"
            else:
                row["status"] = "OK"

        rows.append(row)

    valid = [r for r in rows if r.get("edge") is not None]
    if valid:
        best_edge = max(float(r["edge"]) for r in valid)
        for row in valid:
            if abs(float(row["edge"]) - best_edge) <= 0.000001:
                if best_edge > 0:
                    row["status"] = "BEST"
                else:
                    row["status"] = "LEAST_BAD"

    horizon_quality: dict[str, dict[str, Any]] = {}
    for horizon in ("D5", "D20", "D60"):
        vals = [
            float(row[f"{horizon}_acc"])
            for row in rows
            if row.get(f"{horizon}_acc") is not None
        ]
        if vals:
            avg = sum(vals) / len(vals)
            horizon_quality[horizon] = {
                "avg_acc": avg,
                "edge": avg - 0.5,
                "engines": len(vals),
            }
        else:
            horizon_quality[horizon] = {
                "avg_acc": None,
                "edge": None,
                "engines": 0,
            }

    reliable_horizons = [
        (h, item)
        for h, item in horizon_quality.items()
        if item.get("avg_acc") is not None
    ]

    most_reliable_horizon = None
    if reliable_horizons:
        most_reliable_horizon = max(
            reliable_horizons,
            key=lambda pair: float(pair[1]["avg_acc"]),
        )[0]

    hurting = [
        row["engine"]
        for row in rows
        if row.get("status") in {"BAD", "WEAK", "LEAST_BAD"}
    ]

    least_bad_engine = next((r["engine"] for r in rows if r.get("status") == "LEAST_BAD"), None)

    result = {
        "source": "storage/prediction latest evaluation artifacts",
        "horizons_found": sorted(horizons.keys()),
        "rows": rows,
        "horizon_quality": horizon_quality,
        "most_reliable_horizon": most_reliable_horizon,
        "best_engine": next((r["engine"] for r in rows if r.get("status") == "BEST"), None),
        "least_bad_engine": least_bad_engine,
        "hurting_engines": hurting,
    }

    Path("storage/reports").mkdir(parents=True, exist_ok=True)
    Path("storage/reports/latest_engine_scoreboard.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return result


def _fmt_acc(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.3f}"
    except Exception:
        return "-"


def _fmt_edge(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):+.3f}"
    except Exception:
        return "-"


def print_scoreboard(result: dict[str, Any]) -> None:
    print("AURUM ENGINE SCOREBOARD")
    print("-" * 80)
    print(f"{'engine':<20} {'backend':<9} {'D5_acc':>7} {'D20_acc':>8} {'D60_acc':>8} {'edge':>8} {'status':<8}")

    for row in result.get("rows", []):
        print(
            f"{row.get('engine', '-'):<20} "
            f"{row.get('backend', '-'):<9} "
            f"{_fmt_acc(row.get('D5_acc')):>7} "
            f"{_fmt_acc(row.get('D20_acc')):>8} "
            f"{_fmt_acc(row.get('D60_acc')):>8} "
            f"{_fmt_edge(row.get('edge')):>8} "
            f"{row.get('status', '-'):<8}"
        )

    print()
    print("ENGINE READ")
    print("-" * 80)
    print(f"{'best_engine':<24} {result.get('best_engine') or '-'}")
    print(f"{'least_bad_engine':<24} {result.get('least_bad_engine') or '-'}")
    print(f"{'most_reliable_horizon':<24} {result.get('most_reliable_horizon') or '-'}")

    hurting = result.get("hurting_engines") or []
    print(f"{'hurting_engines':<24} {', '.join(hurting) if hurting else 'none'}")

    print()
    print("HORIZON RELIABILITY")
    print("-" * 80)
    print(f"{'horizon':<10} {'avg_acc':>8} {'edge':>8} {'engines':>8}")

    for horizon, item in (result.get("horizon_quality") or {}).items():
        print(
            f"{horizon:<10} "
            f"{_fmt_acc(item.get('avg_acc')):>8} "
            f"{_fmt_edge(item.get('edge')):>8} "
            f"{int(item.get('engines') or 0):>8}"
        )
