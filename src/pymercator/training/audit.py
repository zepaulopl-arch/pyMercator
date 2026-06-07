from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .history import now_run_id, append_history, save_latest_audit


EVALUATION_CANDIDATES = [
    Path("storage/prediction/latest_multi_horizon_evaluation.json"),
    Path("storage/prediction/latest_evaluation.json"),
]

ENGINE_SCOREBOARD = Path("storage/reports/latest_engine_scoreboard.json")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


def _latest_evaluation() -> tuple[Path | None, dict[str, Any]]:
    for path in EVALUATION_CANDIDATES:
        data = _read_json(path)
        if data:
            return path, data
    return None, {}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _fmt(value: Any, digits: int = 4) -> str:
    try:
        return f"{float(value):+.{digits}f}"
    except Exception:
        return "-"


def _horizon_edges(payload: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}

    # Prefer scoreboard rows if available in payload shape.
    horizon_scoreboard = payload.get("horizon_scoreboard")
    if isinstance(horizon_scoreboard, list):
        for row in horizon_scoreboard:
            if not isinstance(row, dict):
                continue
            hz = str(row.get("horizon") or row.get("HZ") or "").upper()
            if hz in {"D5", "D20", "D60"}:
                if "edge" in row:
                    out[hz] = _to_float(row.get("edge"))
                elif "acc" in row:
                    out[hz] = _to_float(row.get("acc")) - 0.5

    # Fallback from horizon_observer scores: score = acc * 100.
    observer = payload.get("horizon_observer")
    if isinstance(observer, dict):
        scores = observer.get("scores") or observer.get("horizon_scores") or {}
        if isinstance(scores, dict):
            for hz in ("D5", "D20", "D60"):
                if hz in scores and hz not in out:
                    out[hz] = (_to_float(scores.get(hz)) / 100.0) - 0.5

    # Fallback from horizon_scores at root.
    scores = payload.get("horizon_scores")
    if isinstance(scores, dict):
        for hz in ("D5", "D20", "D60"):
            if hz in scores and hz not in out:
                out[hz] = (_to_float(scores.get(hz)) / 100.0) - 0.5

    return out


def _features_missing(payload: dict[str, Any]) -> int:
    raw = int(_to_float(payload.get("raw_features"), 0.0))
    used = int(_to_float(payload.get("features_used"), 0.0))

    if raw > used:
        return raw - used

    removed = int(_to_float(payload.get("removed_features"), 0.0))
    return max(0, removed)


def _engines_used(payload: dict[str, Any]) -> tuple[int, str]:
    engines = payload.get("base_engines") or payload.get("engines") or []

    if isinstance(engines, dict):
        names = list(engines.keys())
    elif isinstance(engines, list):
        names = [str(x) for x in engines]
    else:
        names = []

    # Keep only base sklearn engines for count if possible.
    base = [x for x in names if x in {"extratrees", "randomforest", "gradientboosting"}]
    if base:
        names = base

    return len(names), ",".join(names)


def _status_from_payload(payload: dict[str, Any], global_edge: float) -> str:
    behavior = str(payload.get("behavior") or "").upper()
    quality = str(payload.get("quality") or "").upper()

    if behavior in {"AVOID", "BLOCK", "BLOCKED"}:
        return "NOT_TRADABLE"

    if quality == "WEAK":
        return "OBSERVABLE"

    if global_edge <= 0:
        return "OBSERVABLE"

    if global_edge > 0.03 and quality in {"OK", "STRONG"}:
        return "OPERABLE"

    return "OBSERVABLE"


def _verdict_from_edges(edges: dict[str, float], global_edge: float) -> str:
    positives = [hz for hz, edge in edges.items() if edge > 0]

    if global_edge > 0 and len(positives) >= 2:
        return "BETTER"

    if global_edge > 0 and positives == ["D60"]:
        return "D60_ONLY"

    if global_edge > 0 and "D60" in positives:
        return "WATCH"

    if global_edge <= 0:
        return "WEAK"

    return "UNKNOWN"


def build_train_audit(record: bool = True) -> dict[str, Any]:
    source, payload = _latest_evaluation()

    if not payload:
        result = {
            "run_id": now_run_id(),
            "status": "NO_EVALUATION",
            "source": None,
        }
        save_latest_audit(result)
        return result

    observer = payload.get("horizon_observer")
    if not isinstance(observer, dict):
        observer = payload.get("observer") if isinstance(payload.get("observer"), dict) else {}

    edges = _horizon_edges(payload)
    # Prefer observer combined_score, because final adaptive observer may live there.
    observer_combined = None
    if isinstance(observer, dict):
        observer_combined = observer.get("combined_score")

    root_combined = payload.get("combined_score")

    if observer_combined is not None:
        global_edge = _to_float(observer_combined, 50.0) / 100.0 - 0.5
    elif root_combined is not None:
        global_edge = _to_float(root_combined, 50.0) / 100.0 - 0.5
    else:
        global_edge = _to_float(payload.get("edge"), _to_float(payload.get("global_edge"), 0.0))

    engines_count, engines_text = _engines_used(payload)

    engine_scoreboard = _read_json(ENGINE_SCOREBOARD)

    run_id = now_run_id()

    result = {
        "run_id": run_id,
        "created_at": run_id,
        "source": str(source) if source else "-",
        "features_used": int(_to_float(payload.get("features_used"), 0.0)),
        "raw_features": int(_to_float(payload.get("raw_features"), 0.0)),
        "canonical_features": int(_to_float(payload.get("canonical_features"), payload.get("features_used") or 0)),
        "removed_features": int(_to_float(payload.get("removed_features"), 0.0)),
        "features_missing": _features_missing(payload),
        "engines_used": engines_count,
        "engines": engines_text,
        "horizons": ",".join(
            f"D{str(x).replace('D', '').replace('d', '')}"
            for x in payload.get("horizons", ["D5", "D20", "D60"])
        ),
        "meta_model": str(payload.get("meta_model") or "ridge"),
        "observer": str(observer.get("mode") or payload.get("observer_mode") or "-"),
        "quality": str(
            payload.get("quality")
            or observer.get("quality")
            or ("STRONG" if global_edge >= 0.10 else "OK" if global_edge > 0.0 else "WEAK")
        ),
        "edge": global_edge,
        "global_edge": global_edge,
        "D5_edge": edges.get("D5"),
        "D20_edge": edges.get("D20"),
        "D60_edge": edges.get("D60"),
        "status": _status_from_payload(payload, global_edge),
        "verdict": _verdict_from_edges(edges, global_edge),
        "most_reliable_horizon": engine_scoreboard.get("most_reliable_horizon") or "-",
        "best_engine": engine_scoreboard.get("best_engine") or "-",
        "least_bad_engine": engine_scoreboard.get("least_bad_engine") or "-",
        "tradability": _status_from_payload(payload, global_edge),
    }

    save_latest_audit(result)

    if record:
        append_history({
            **result,
            "D5_edge": _fmt(result.get("D5_edge")),
            "D20_edge": _fmt(result.get("D20_edge")),
            "D60_edge": _fmt(result.get("D60_edge")),
            "global_edge": _fmt(result.get("global_edge")),
            "edge": _fmt(result.get("edge")),
        })

    return result


def print_train_audit(result: dict[str, Any]) -> None:
    print("AURUM TRAIN AUDIT")
    print("-" * 80)

    if result.get("status") == "NO_EVALUATION":
        print("status                  NO_EVALUATION")
        print("source                  -")
        return

    rows = [
        ("run_id", result.get("run_id")),
        ("features_used", result.get("features_used")),
        ("features_missing", result.get("features_missing")),
        ("raw_features", result.get("raw_features")),
        ("canonical_features", result.get("canonical_features")),
        ("removed_features", result.get("removed_features")),
        ("engines_used", result.get("engines_used")),
        ("engines", result.get("engines")),
        ("horizons", result.get("horizons")),
        ("meta_model", result.get("meta_model")),
        ("observer", result.get("observer")),
        ("quality", result.get("quality")),
        ("edge", _fmt(result.get("edge"))),
        ("D5_edge", _fmt(result.get("D5_edge"))),
        ("D20_edge", _fmt(result.get("D20_edge"))),
        ("D60_edge", _fmt(result.get("D60_edge"))),
        ("most_reliable_horizon", result.get("most_reliable_horizon")),
        ("best_engine", result.get("best_engine")),
        ("least_bad_engine", result.get("least_bad_engine")),
        ("status", result.get("status")),
        ("verdict", result.get("verdict")),
    ]

    for key, value in rows:
        print(f"{key:<24} {value if value is not None else '-'}")
