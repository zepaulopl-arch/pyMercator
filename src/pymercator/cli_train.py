from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pymercator.legacy_prediction_engines import (
    CATBOOST_AVAILABLE,
    SKLEARN_AVAILABLE,
    XGBOOST_AVAILABLE,
)
from pymercator.prediction_config import effective_prediction_config, horizon_key
from pymercator.prediction_lab import run_prediction_lab

ENGINE_ALIASES = {
}

REAL_ENGINES = {"extratrees", "randomforest", "gradientboosting", "ridge_ensemble"}
BASELINE_ENGINES = {"rolling_majority"}
PROFILE_IGNORED_WARNING = "WARNING: --profile is ignored by train. Profiles are applied in run."


def engine_availability() -> dict[str, bool]:
    return {
        "sklearn_available": bool(SKLEARN_AVAILABLE),
        "xgboost_available": bool(XGBOOST_AVAILABLE),
        "catboost_available": bool(CATBOOST_AVAILABLE),
    }


def default_train_engines() -> list[str]:
    return ["ridge_ensemble"]


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


def _trained_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _primary_metrics(payload: dict[str, Any], engine_used: str) -> dict[str, Any]:
    models = payload.get("evaluation", {}).get("models", {})
    if isinstance(models, dict) and isinstance(models.get(engine_used), dict):
        return dict(models[engine_used])
    return {}


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


def _score_from_metrics(metrics: dict[str, Any]) -> float:
    accuracy = float(metrics.get("accuracy", 0.0) or 0.0)
    return round(accuracy * 100.0 if accuracy <= 1.0 else accuracy, 4)


def _signal(score: float) -> str:
    if score >= 60.0:
        return "strong"
    if score >= 50.0:
        return "neutral"
    return "weak"


def _behavior(score_by_horizon: dict[str, float]) -> str:
    d5 = _signal(score_by_horizon.get("D5", 0.0)) == "strong"
    d20 = _signal(score_by_horizon.get("D20", 0.0)) == "strong"
    d60 = _signal(score_by_horizon.get("D60", 0.0)) == "strong"

    if d5 and d20 and d60:
        return "TREND_CONFIRM"
    if d5 and d20 and not d60:
        return "SWING"
    if d5 and not d20 and not d60:
        return "TACTICAL"
    if not d5 and d20 and d60:
        return "POSITIONAL_SETUP"
    if not d5 and not d20 and d60:
        return "POSITIONAL_EARLY"
    if d5 and not d20 and d60:
        return "DIVERGENT"
    if not d5 and not d20 and not d60:
        return "AVOID"
    return "SWING_WAIT"


def _observer_summary(
    *,
    horizon_models: dict[str, Any],
    observer_config: dict[str, Any],
) -> dict[str, Any]:
    scores = {
        key: _score_from_metrics(model.get("ensemble_metrics", {}))
        for key, model in horizon_models.items()
    }
    weights = {
        str(key).upper(): float(value)
        for key, value in observer_config.get("weights", {}).items()
    }
    if not weights:
        weight = 1.0 / max(1, len(scores))
        weights = {key: weight for key in scores}

    total_weight = sum(weights.get(key, 0.0) for key in scores) or 1.0
    combined_score = round(
        sum(scores[key] * weights.get(key, 0.0) for key in scores) / total_weight,
        4,
    )
    dominant_horizon = max(scores, key=lambda key: scores[key]) if scores else "-"

    return {
        "engine_used": "horizon_observer",
        "mode": observer_config.get("mode", "weighted"),
        "inputs": list(horizon_models),
        "independent_analysis": bool(observer_config.get("independent_analysis", True)),
        "combined_analysis": bool(observer_config.get("combined_analysis", True)),
        "weights": weights,
        "scores": scores,
        "combined_score": combined_score,
        "dominant_horizon": dominant_horizon,
        "behavior": _behavior(scores),
        "behavior_labels": [
            "TACTICAL",
            "SWING",
            "POSITIONAL_SETUP",
            "POSITIONAL_EARLY",
            "TREND_CONFIRM",
            "DIVERGENT",
            "AVOID",
        ],
        "status": "OK" if scores else "FAIL",
    }


def _multi_horizon_status(horizon_models: dict[str, Any]) -> tuple[str, str]:
    statuses = [str(model.get("status", "FAIL")) for model in horizon_models.values()]
    valid_count = sum(1 for status in statuses if status in {"OK", "DEGRADED"})

    if statuses and all(status == "OK" for status in statuses):
        return "OK", ""
    if valid_count >= 2:
        return "DEGRADED", "one or more horizons failed or degraded"
    return "FAIL", "multi_horizon_ridge requires at least 2 valid horizons"


def _prediction_output_root(evaluation_output: str | Path) -> Path:
    return Path(evaluation_output).parent


def run_train_flow(
    *,
    profile: str = "",
    horizon: int = 5,
    horizons: list[int] | str | None = None,
    config_path: str = "config/prediction.json",
    matrix: str = "storage/features/latest_feature_matrix.csv",
    prices_dir: str = "data/prices",
    dataset_output: str = "storage/prediction/latest_dataset.csv",
    evaluation_output: str = "storage/prediction/latest_evaluation.json",
    min_history: int | None = None,
    min_train_rows: int | None = None,
    engines: list[str] | None = None,
    base_engines: list[str] | str | None = None,
    meta_model: str | None = None,
    observer_mode: str | None = None,
    weights: str | dict[str, float] | None = None,
    independent_horizons: bool = False,
    combined_horizons: bool = False,
    explicit_engines: bool = False,
    n_jobs: int | None = None,
    autotune: bool | None = None,
    autotune_iter: int | None = None,
    autotune_cv: int | None = None,
) -> dict[str, Any]:
    config = effective_prediction_config(
        path=config_path,
        overrides={
            "horizons": horizons,
            "base_engines": base_engines,
            "meta_model": meta_model,
            "observer_mode": observer_mode,
            "weights": weights,
            "independent_horizons": independent_horizons,
            "combined_horizons": combined_horizons,
            "min_history": min_history,
            "min_train_rows": min_train_rows,
            "n_jobs": n_jobs,
            "autotune": autotune,
            "autotune_iter": autotune_iter,
            "autotune_cv": autotune_cv,
        },
    )
    training = config.get("training", {})
    selected_horizons = [int(item) for item in config.get("horizons", [horizon])]
    selected_base_engines = [str(item) for item in config.get("base_engines", [])]
    selected_meta = str(config.get("meta_model", "ridge")).lower()
    selected_engines = list(engines or default_train_engines())
    selected_n_jobs = int(training.get("n_jobs", 4))
    selected_min_history = int(training.get("min_history", 120))
    selected_min_train_rows = int(training.get("min_train_rows", 100))
    selected_autotune = bool(training.get("autotune", False))
    selected_autotune_iter = int(training.get("autotune_iter", 20))
    selected_autotune_cv = int(training.get("autotune_cv", 3))
    output_root = _prediction_output_root(evaluation_output)
    files = {
        "matrix": matrix,
        "prices_dir": prices_dir,
        "dataset": dataset_output,
        "evaluation": evaluation_output,
        "multi_horizon_evaluation": str(output_root / "latest_multi_horizon_evaluation.json"),
    }

    if not Path(matrix).exists():
        return {
            "command": "train",
            "horizons": selected_horizons,
            "status": "BLOCKED",
            "reason": "feature matrix not found",
            "required": 1,
            "found": 0,
            "files": files,
        }

    if not Path(prices_dir).exists():
        return {
            "command": "train",
            "horizons": selected_horizons,
            "status": "BLOCKED",
            "reason": "prices directory not found",
            "required": 1,
            "found": 0,
            "files": files,
        }

    if selected_meta != "ridge":
        return {
            "command": "train",
            "horizons": selected_horizons,
            "status": "FAIL",
            "reason": f"unsupported meta model: {selected_meta}",
            "files": files,
        }

    baseline_requested = explicit_engines and selected_engines == ["rolling_majority"]
    valid_train_engines = REAL_ENGINES | BASELINE_ENGINES
    unknown_engines = [engine for engine in selected_engines if engine not in valid_train_engines]
    if explicit_engines and unknown_engines:
        return {
            "command": "train",
            "horizons": selected_horizons,
            "status": "FAIL",
            "reason": (
                "Unknown prediction engines: "
                f"{', '.join(unknown_engines)}. "
                "Valid train engines: rolling_majority, extratrees, "
                "randomforest, gradientboosting, ridge_ensemble"
            ),
            "files": files,
        }
    if explicit_engines and "rolling_majority" in selected_engines and not baseline_requested:
        return {
            "command": "train",
            "horizons": selected_horizons,
            "status": "FAIL",
            "reason": "rolling_majority cannot be mixed with real engines",
            "files": files,
        }

    if explicit_engines and not baseline_requested:
        selected_base_engines = [
            engine
            for engine in selected_engines
            if engine in REAL_ENGINES and engine != "ridge_ensemble"
        ] or selected_base_engines

    availability = engine_availability()

    def run_lab(
        *,
        selected_horizon: int,
        selected: list[str],
        selected_dataset_output: str,
        selected_evaluation_output: str,
    ) -> dict[str, Any]:
        return run_prediction_lab(
            matrix=matrix,
            prices_dir=prices_dir,
            dataset_output=selected_dataset_output,
            evaluation_output=selected_evaluation_output,
            horizon=selected_horizon,
            min_history=selected_min_history,
            min_train_rows=selected_min_train_rows,
            engines=selected,
            base_engines=selected_base_engines,
            n_jobs=max(1, int(selected_n_jobs)),
            autotune=selected_autotune,
            autotune_iter=selected_autotune_iter,
            autotune_cv=selected_autotune_cv,
        )

    if baseline_requested:
        try:
            payload = run_lab(
                selected_horizon=selected_horizons[0],
                selected=["rolling_majority"],
                selected_dataset_output=dataset_output,
                selected_evaluation_output=evaluation_output,
            )
        except Exception as exc:
            return {
                "command": "train",
                "horizons": selected_horizons,
                "status": "FAIL",
                "reason": str(exc),
                "detail": {"error": str(exc)},
                "files": files,
            }

        dataset_rows = int(payload.get("dataset", {}).get("rows", 0))
        evaluation_payload = payload.get("evaluation", {})
        assets = _csv_unique_assets(dataset_output)
        engine_used = str(evaluation_payload.get("engine_used") or "rolling_majority")
        trained_at = _trained_at()
        metrics = _primary_metrics(payload, engine_used)
        metadata = {
            "engine_used": engine_used,
            "is_baseline": True,
            "status": "BASELINE",
            "horizons": [selected_horizons[0]],
            "rows": dataset_rows,
            "assets": assets,
            "trained_at": trained_at,
            "metrics": metrics,
            "training": {
                "n_jobs": selected_n_jobs,
                "autotune": selected_autotune,
                "autotune_iter": selected_autotune_iter,
                "autotune_cv": selected_autotune_cv,
                "min_history": selected_min_history,
                "min_train_rows": selected_min_train_rows,
            },
            **availability,
        }
        _write_evaluation_metadata(path=evaluation_output, metadata=metadata)
        return {
            "command": "train",
            "horizons": [selected_horizons[0]],
            "status": "BASELINE",
            "engine_used": engine_used,
            "is_baseline": True,
            "base_engines": [],
            "meta_model": "",
            "observer": {},
            "training": metadata["training"],
            "dataset": {"rows": dataset_rows, "assets": assets, "output": dataset_output},
            "evaluation": {
                "engine_used": engine_used,
                "is_baseline": True,
                "metrics": metrics,
                "output": evaluation_output,
            },
            "files": files,
        }

    horizon_models: dict[str, Any] = {}
    total_rows = 0
    assets = 0

    for selected_horizon in selected_horizons:
        key = horizon_key(selected_horizon)
        horizon_dir = output_root / key.lower()
        horizon_dataset = horizon_dir / "latest_dataset.csv"
        horizon_evaluation = horizon_dir / "latest_evaluation.json"
        try:
            payload = run_lab(
                selected_horizon=selected_horizon,
                selected=["ridge_ensemble"],
                selected_dataset_output=str(horizon_dataset),
                selected_evaluation_output=str(horizon_evaluation),
            )
        except Exception as exc:
            horizon_models[key] = {
                "engine_used": "ridge_ensemble",
                "base_engines": selected_base_engines,
                "meta_model": selected_meta,
                "status": "FAIL",
                "reason": str(exc),
                "output": str(horizon_evaluation),
            }
            continue

        evaluation_payload = payload.get("evaluation", {})
        total_rows += int(payload.get("dataset", {}).get("rows", 0))
        assets = max(assets, _csv_unique_assets(horizon_dataset))
        horizon_models[key] = {
            "engine_used": evaluation_payload.get("engine_used", "ridge_ensemble"),
            "base_engines": evaluation_payload.get("base_engines", selected_base_engines),
            "valid_base_engines": evaluation_payload.get("valid_base_engines", []),
            "failed_engines": evaluation_payload.get("failed_engines", []),
            "meta_model": evaluation_payload.get("meta_model", selected_meta),
            "base_metrics": evaluation_payload.get("base_metrics", {}),
            "ridge_coefficients": evaluation_payload.get("ridge_coefficients", {}),
            "ensemble_metrics": evaluation_payload.get("ensemble_metrics", {}),
            "status": evaluation_payload.get("status", payload.get("status", "OK")),
            "reason": evaluation_payload.get("reason", ""),
            "dataset_output": str(horizon_dataset),
            "output": str(horizon_evaluation),
            "rows": int(evaluation_payload.get("rows", 0)),
            "evaluated_rows": int(evaluation_payload.get("evaluated_rows", 0)),
        }

    status, reason = _multi_horizon_status(horizon_models)
    observer = _observer_summary(
        horizon_models=horizon_models,
        observer_config=config.get("observer", {}),
    )
    trained_at = _trained_at()
    final_payload = {
        "engine_used": "multi_horizon_ridge",
        "is_baseline": False,
        "trained_models": ["multi_horizon_ridge"],
        "status": status,
        "reason": reason,
        "horizons": selected_horizons,
        "base_engines": selected_base_engines,
        "meta_model": selected_meta,
        "observer": {
            "mode": config.get("observer", {}).get("mode", "weighted"),
            "independent_analysis": bool(
                config.get("observer", {}).get("independent_analysis", True)
            ),
            "combined_analysis": bool(config.get("observer", {}).get("combined_analysis", True)),
            "weights": observer.get("weights", {}),
        },
        "training": {
            "n_jobs": selected_n_jobs,
            "autotune": selected_autotune,
            "autotune_iter": selected_autotune_iter,
            "autotune_cv": selected_autotune_cv,
            "min_history": selected_min_history,
            "min_train_rows": selected_min_train_rows,
            "temporal_split": True,
            "shuffle": False,
        },
        "horizon_models": horizon_models,
        "horizon_observer": observer,
        "rows": total_rows,
        "assets": assets,
        "trained_at": trained_at,
        "metrics": {
            "combined_score": observer.get("combined_score", 0.0),
            "dominant_horizon": observer.get("dominant_horizon", "-"),
            "behavior": observer.get("behavior", "AVOID"),
        },
        **availability,
    }

    multi_output = Path(files["multi_horizon_evaluation"])
    multi_output.parent.mkdir(parents=True, exist_ok=True)
    multi_output.write_text(
        json.dumps(final_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    Path(evaluation_output).parent.mkdir(parents=True, exist_ok=True)
    Path(evaluation_output).write_text(
        json.dumps(final_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "command": "train",
        "horizons": selected_horizons,
        "status": status,
        "reason": reason,
        "engine_used": "multi_horizon_ridge",
        "is_baseline": False,
        "trained_models": ["multi_horizon_ridge"],
        "base_engines": selected_base_engines,
        "meta_model": selected_meta,
        "observer": final_payload["observer"],
        "horizon_observer": observer,
        "training": final_payload["training"],
        "dataset": {"rows": total_rows, "assets": assets, "output": str(output_root)},
        "evaluation": {
            "engine_used": "multi_horizon_ridge",
            "is_baseline": False,
            "horizons": selected_horizons,
            "base_engines": selected_base_engines,
            "meta_model": selected_meta,
            "status": status,
            "reason": reason,
            "output": evaluation_output,
            "multi_output": str(multi_output),
        },
        "horizon_models": horizon_models,
        "files": files,
        "payload": final_payload,
    }


def render_train_summary(payload: dict[str, Any]) -> str:
    status = payload.get("status", "-")
    lines = [f"TRAIN | STATUS {status}"]

    if status == "BLOCKED":
        lines.extend(
            [
                f"REASON: {payload.get('reason', '-')}",
                f"REQUIRED: {payload.get('required', '-')}",
                f"FOUND: {payload.get('found', '-')}",
            ]
        )
        return "\n".join(lines)

    if status == "FAIL":
        if payload.get("engine_used"):
            lines.append(f"ENGINE: {payload.get('engine_used')}")
        lines.append(f"REASON: {payload.get('reason', '-')}")
        if payload.get("failed_engines"):
            lines.append(f"FAILED_ENGINES: {', '.join(payload.get('failed_engines', []))}")
        return "\n".join(lines)

    if status not in {"OK", "DEGRADED"}:
        if status not in {"FALLBACK", "BASELINE"}:
            lines.append(f"REASON: {payload.get('reason', '-')}")
            return "\n".join(lines)

    dataset = payload.get("dataset", {})
    evaluation = payload.get("evaluation", {})
    training = payload.get("training", {})

    lines.extend(
        [
            f"ENGINE: {payload.get('engine_used', '-')}",
            f"HORIZONS: {','.join(horizon_key(item) for item in payload.get('horizons', []))}",
            f"BASE ENGINES: {','.join(payload.get('base_engines', []))}",
            f"META: {payload.get('meta_model', '-')}",
            f"OBSERVER: {payload.get('observer', {}).get('mode', '-')}",
            f"AUTOTUNE: {'ON' if training.get('autotune') else 'OFF'}",
            f"BASELINE: {str(payload.get('is_baseline', False)).lower()}",
            "",
            "DATASET:",
            f"- rows: {dataset.get('rows', 0)}",
            f"- assets: {dataset.get('assets', 0)}",
            f"- output: {dataset.get('output', '-')}",
            "",
            "EVALUATION:",
            f"- engine: {payload.get('engine_used', '-')}",
            f"- baseline: {str(payload.get('is_baseline', False)).lower()}",
        ]
    )
    if evaluation.get("base_engines"):
        lines.append(f"- base_engines: {', '.join(evaluation.get('base_engines', []))}")
    if evaluation.get("meta_model"):
        lines.append(f"- meta_model: {evaluation.get('meta_model')}")
    if evaluation.get("failed_engines"):
        lines.append(f"- failed_engines: {', '.join(evaluation.get('failed_engines', []))}")
    lines.extend(
        [
            f"- status: {status}",
            f"- output: {evaluation.get('output', '-')}",
        ]
    )
    return "\n".join(lines)


def run_train_command(args: Any) -> int:
    if str(getattr(args, "profile", "") or "").strip():
        print(PROFILE_IGNORED_WARNING, file=sys.stderr)

    requested_horizons: str | list[int] | None = getattr(args, "horizons", "")
    if not requested_horizons and getattr(args, "horizon", None) is not None:
        requested_horizons = [int(args.horizon)]

    payload = run_train_flow(
        profile=getattr(args, "profile", ""),
        horizon=int(getattr(args, "horizon", 5) or 5),
        horizons=requested_horizons,
        config_path=getattr(args, "config", "config/prediction.json"),
        matrix=args.matrix,
        prices_dir=args.prices_dir,
        dataset_output=args.dataset_output,
        evaluation_output=args.evaluation_output,
        min_history=getattr(args, "min_history", None),
        min_train_rows=getattr(args, "min_train_rows", None),
        engines=parse_engines(args.engines),
        base_engines=args.engines,
        meta_model=getattr(args, "meta", None),
        observer_mode=getattr(args, "observer", None),
        weights=getattr(args, "weights", None),
        independent_horizons=bool(getattr(args, "independent_horizons", False)),
        combined_horizons=bool(getattr(args, "combined_horizons", False)),
        explicit_engines=bool(str(args.engines or "").strip()),
        n_jobs=getattr(args, "n_jobs", None),
        autotune=getattr(args, "autotune", None),
        autotune_iter=getattr(args, "autotune_iter", None),
        autotune_cv=getattr(args, "autotune_cv", None),
    )

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_train_summary(payload))

    return 0 if payload["status"] in {"OK", "DEGRADED", "BASELINE"} else 1
