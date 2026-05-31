from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from pymercator.legacy_prediction_engines import (
    CATBOOST_AVAILABLE,
    SKLEARN_AVAILABLE,
    XGBOOST_AVAILABLE,
)
from pymercator.policy import normalize_profile
from pymercator.prediction_lab import run_prediction_lab

ENGINE_ALIASES = {
    "xgboost": "xgb",
}

ENGINE_BLOCKING_STATUSES = {"NO_BASE_ENGINES", "NO_DATA", "UNAVAILABLE"}
REAL_ENGINES = {"extratrees", "xgb", "catboost", "ridge_arbiter"}
BASELINE_ENGINES = {"rolling_majority", "momentum_rule"}
FALLBACK_REASON = "prediction engines unavailable or failed"


def engine_availability() -> dict[str, bool]:
    return {
        "sklearn_available": bool(SKLEARN_AVAILABLE),
        "xgboost_available": bool(XGBOOST_AVAILABLE),
        "catboost_available": bool(CATBOOST_AVAILABLE),
    }


def default_train_engines() -> list[str]:
    if SKLEARN_AVAILABLE:
        return ["extratrees"]

    if XGBOOST_AVAILABLE:
        return ["xgb"]

    if CATBOOST_AVAILABLE:
        return ["catboost"]

    return ["rolling_majority"]


def parse_engines(value: str) -> list[str]:
    if not value:
        return default_train_engines()

    engines: list[str] = []
    for item in value.split(","):
        engine = item.strip().lower()
        if not engine:
            continue
        engines.append(ENGINE_ALIASES.get(engine, engine))
    return engines or default_train_engines()


def _real_ok_engines(engines: list[str], engine_status: dict[str, Any]) -> list[str]:
    return [
        engine
        for engine in engines
        if engine in REAL_ENGINES and engine_status.get(engine) == "OK"
    ]


def _baseline_engines(engines: list[str]) -> list[str]:
    return [engine for engine in engines if engine in BASELINE_ENGINES]


def _engine_display_name(engine: str) -> str:
    if engine == "xgb":
        return "xgboost/xgb"
    return engine


def _short_error(text: str, limit: int = 120) -> str:
    compact = " ".join(str(text or "unavailable").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _fallback_reason_for(engines: list[str], detail: str) -> str:
    failed = [engine for engine in engines if engine in {"extratrees", "xgb", "catboost"}]
    if len(failed) == 1:
        return f"{_engine_display_name(failed[0])} failed: {_short_error(detail)}"
    if failed:
        return f"real engines failed: {_short_error(detail)}"
    return FALLBACK_REASON


def _csv_unique_assets(path: str | Path) -> int:
    source = Path(path)
    if not source.exists():
        return 0

    with source.open("r", encoding="utf-8-sig", newline="") as file:
        return len(
            {
                str(row.get("ticker", "")).strip().upper()
                for row in csv.DictReader(file)
                if str(row.get("ticker", "")).strip()
            }
        )


def _write_evaluation_metadata(
    *,
    path: str | Path,
    metadata: dict[str, Any],
) -> None:
    output = Path(path)
    payload: dict[str, Any] = {}

    if output.exists():
        payload = json.loads(output.read_text(encoding="utf-8-sig"))

    payload.update(metadata)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_train_flow(
    *,
    profile: str = "CON",
    horizon: int = 5,
    matrix: str = "storage/features/latest_feature_matrix.csv",
    prices_dir: str = "data/prices",
    dataset_output: str = "storage/prediction/latest_dataset.csv",
    evaluation_output: str = "storage/prediction/latest_evaluation.json",
    min_history: int = 20,
    min_train_rows: int = 100,
    engines: list[str] | None = None,
    explicit_engines: bool = False,
    n_jobs: int = 4,
    autotune: bool = False,
) -> dict[str, Any]:
    normalized_profile = normalize_profile(profile)
    files = {
        "matrix": matrix,
        "prices_dir": prices_dir,
        "dataset": dataset_output,
        "evaluation": evaluation_output,
    }

    if not Path(matrix).exists():
        return {
            "command": "train",
            "profile": normalized_profile,
            "horizon": horizon,
            "status": "BLOCKED",
            "reason": "feature matrix not found",
            "required": 1,
            "found": 0,
            "files": files,
        }

    if not Path(prices_dir).exists():
        return {
            "command": "train",
            "profile": normalized_profile,
            "horizon": horizon,
            "status": "BLOCKED",
            "reason": "prices directory not found",
            "required": 1,
            "found": 0,
            "files": files,
        }

    selected_engines = list(engines or default_train_engines())
    selected_real_engines = [engine for engine in selected_engines if engine in REAL_ENGINES]
    fallback_reason = ""
    real_failure_detail = ""
    availability = engine_availability()

    def run_lab(selected: list[str]) -> dict[str, Any]:
        return run_prediction_lab(
            matrix=matrix,
            prices_dir=prices_dir,
            dataset_output=dataset_output,
            evaluation_output=evaluation_output,
            horizon=horizon,
            min_history=min_history,
            min_train_rows=min_train_rows,
            engines=selected,
            n_jobs=max(1, int(n_jobs)),
            autotune=autotune,
        )

    try:
        payload = run_lab(selected_engines)
    except Exception as exc:
        if not selected_real_engines:
            return {
                "command": "train",
                "profile": normalized_profile,
                "horizon": horizon,
                "status": "FAIL",
                "reason": str(exc),
                "detail": {"error": str(exc)},
                "files": files,
            }

        real_failure_detail = str(exc)
        fallback_reason = _fallback_reason_for(selected_real_engines, real_failure_detail)
        selected_engines = ["rolling_majority"]
        selected_real_engines = []
        payload = run_lab(selected_engines)

    dataset_rows = int(payload.get("dataset", {}).get("rows", 0))
    evaluated_rows = int(payload.get("evaluation", {}).get("evaluated_rows", 0))
    engine_status = payload.get("evaluation", {}).get("engine_status", {})
    real_ok = _real_ok_engines(selected_engines, engine_status)
    blocked_real_engines = [
        engine
        for engine in selected_real_engines
        if engine_status.get(engine) in ENGINE_BLOCKING_STATUSES
    ]
    missing_real_engines = [
        engine
        for engine in selected_real_engines
        if not engine_status.get(engine)
    ]

    if dataset_rows < min_train_rows or evaluated_rows == 0:
        return {
            "command": "train",
            "profile": normalized_profile,
            "horizon": horizon,
            "status": "BLOCKED",
            "reason": "insufficient training rows",
            "required": min_train_rows,
            "found": dataset_rows,
            "payload": payload,
            "files": files,
        }

    if selected_real_engines and not real_ok:
        if not real_failure_detail:
            failed = blocked_real_engines or missing_real_engines or selected_real_engines
            real_failure_detail = ", ".join(
                f"{_engine_display_name(engine)}: {engine_status.get(engine, 'NO_STATUS')}"
                for engine in failed
            )
        fallback_reason = _fallback_reason_for(selected_real_engines, real_failure_detail)
        selected_engines = ["rolling_majority"]
        payload = run_lab(selected_engines)
        dataset_rows = int(payload.get("dataset", {}).get("rows", 0))
        evaluated_rows = int(payload.get("evaluation", {}).get("evaluated_rows", 0))
        engine_status = payload.get("evaluation", {}).get("engine_status", {})

    if dataset_rows < min_train_rows or evaluated_rows == 0:
        return {
            "command": "train",
            "profile": normalized_profile,
            "horizon": horizon,
            "status": "BLOCKED",
            "reason": "insufficient training rows",
            "required": min_train_rows,
            "found": dataset_rows,
            "payload": payload,
            "files": files,
        }

    assets = _csv_unique_assets(dataset_output)
    real_ok = _real_ok_engines(selected_engines, engine_status)
    baseline_engines = _baseline_engines(selected_engines)
    engine_used = real_ok[0] if real_ok else (baseline_engines[0] if baseline_engines else "-")
    is_baseline = engine_used in BASELINE_ENGINES

    if real_ok:
        status = "OK"
    elif explicit_engines and baseline_engines and not fallback_reason:
        status = "BASELINE"
    else:
        status = "FALLBACK"
        fallback_reason = fallback_reason or FALLBACK_REASON

    evaluation_metadata = {
        "engine_used": engine_used,
        "is_baseline": is_baseline,
        "trained_models": real_ok,
        "fallback_reason": fallback_reason,
        "rows": dataset_rows,
        "assets": assets,
        "horizon": horizon,
        "profile": normalized_profile,
        "profile_scope": "metadata_only",
        **availability,
    }
    if real_failure_detail:
        evaluation_metadata["real_engine_failure"] = real_failure_detail

    _write_evaluation_metadata(path=evaluation_output, metadata=evaluation_metadata)

    return {
        "command": "train",
        "profile": normalized_profile,
        "horizon": horizon,
        "status": status,
        "engine_used": engine_used,
        "is_baseline": is_baseline,
        "trained_models": real_ok,
        "fallback_reason": fallback_reason,
        "real_engine_failure": real_failure_detail,
        **availability,
        "dataset": {
            "rows": dataset_rows,
            "assets": assets,
            "output": dataset_output,
        },
        "evaluation": {
            "rows": int(payload.get("evaluation", {}).get("rows", 0)),
            "evaluated_rows": evaluated_rows,
            "engines": payload.get("evaluation", {}).get("engines", []),
            "engine_status": engine_status,
            "engine_used": engine_used,
            "is_baseline": is_baseline,
            "trained_models": real_ok,
            "fallback_reason": fallback_reason,
            "real_engine_failure": real_failure_detail,
            **availability,
            "output": evaluation_output,
        },
        "profile_scope": "metadata_only",
        "payload": payload,
        "files": files,
    }


def render_train_summary(payload: dict[str, Any]) -> str:
    status = payload.get("status", "-")
    lines = [
        (
            f"TRAIN | PROFILE {payload.get('profile', '-')} | "
            f"HORIZON {payload.get('horizon', '-')} | STATUS {status}"
        )
    ]

    if status == "BLOCKED":
        lines.extend(
            [
                f"REASON: {payload.get('reason', '-')}",
                f"REQUIRED: {payload.get('required', '-')}",
                f"FOUND: {payload.get('found', '-')}",
            ]
        )
        return "\n".join(lines)

    if status in {"FALLBACK", "BASELINE"}:
        lines.append(f"ENGINE: {payload.get('engine_used', '-')}")
        reason = payload.get("fallback_reason") or "baseline explicitly requested"
        lines.append(f"REASON: {reason}")
        if payload.get("real_engine_failure"):
            lines.append(f"DETAIL: {payload['real_engine_failure']}")

    if status != "OK":
        if status not in {"FALLBACK", "BASELINE"}:
            lines.append(f"REASON: {payload.get('reason', '-')}")
            return "\n".join(lines)

    dataset = payload.get("dataset", {})
    evaluation = payload.get("evaluation", {})
    engine_status = evaluation.get("engine_status", {})
    first_engine = next(iter(engine_status), "")
    if not first_engine:
        first_engine = next(iter(evaluation.get("engines", [])), "-")
    first_status = engine_status.get(first_engine, "OK") if first_engine != "-" else "-"

    lines.extend(
        [
            "",
            "DATASET:",
            f"- rows: {dataset.get('rows', 0)}",
            f"- assets: {dataset.get('assets', 0)}",
            f"- output: {dataset.get('output', '-')}",
            "",
            "EVALUATION:",
            f"- engine: {payload.get('engine_used', first_engine)}",
            f"- baseline: {str(payload.get('is_baseline', False)).lower()}",
            f"- status: {first_status}",
            f"- output: {evaluation.get('output', '-')}",
        ]
    )
    return "\n".join(lines)


def run_train_command(args: Any) -> int:
    payload = run_train_flow(
        profile=args.profile,
        horizon=args.horizon,
        matrix=args.matrix,
        prices_dir=args.prices_dir,
        dataset_output=args.dataset_output,
        evaluation_output=args.evaluation_output,
        min_history=args.min_history,
        min_train_rows=args.min_train_rows,
        engines=parse_engines(args.engines),
        explicit_engines=bool(str(args.engines or "").strip()),
        n_jobs=args.n_jobs,
        autotune=args.autotune,
    )

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_train_summary(payload))

    return 0 if payload["status"] in {"OK", "FALLBACK", "BASELINE"} else 1
