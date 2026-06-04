from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pymercator.artifact_metadata import artifact_metadata
from pymercator.domain import DailyReport
from pymercator.explain import decision_codes, decision_label


def _enum_to_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    return value


def _convert(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _convert(item) for key, item in value.items()}

    if isinstance(value, tuple | list):
        return [_convert(item) for item in value]

    return _enum_to_value(value)


def _prediction_global(prediction: dict[str, Any] | None) -> dict[str, Any]:
    if not prediction:
        return {}

    engine = prediction.get("engine") or prediction.get("engine_used")
    payload = {
        "engine": engine,
        "engine_used": engine,
        "horizons": prediction.get("horizons", []),
        "d5_score": prediction.get("d5_score"),
        "d20_score": prediction.get("d20_score"),
        "d60_score": prediction.get("d60_score"),
        "combined_score": prediction.get("combined_score"),
        "dominant_horizon": prediction.get("dominant_horizon"),
        "behavior": prediction.get("behavior"),
        "horizon_alignment": prediction.get("horizon_alignment"),
        "dominance_strength": prediction.get("dominance_strength"),
        "horizon_scores": prediction.get("horizon_scores"),
        "horizon_spread": prediction.get("horizon_spread"),
        "weights": prediction.get("weights", {}),
        "model_quality": prediction.get("model_quality", {}),
    }
    quality = payload.get("model_quality", {})
    if isinstance(quality, dict):
        payload["model_edge"] = quality.get("edge")
    return {key: value for key, value in payload.items() if value is not None}


def _prediction_for_decision(prediction: dict[str, Any] | None) -> dict[str, Any]:
    global_prediction = _prediction_global(prediction)
    return {
        key: global_prediction.get(key)
        for key in (
            "d5_score",
            "d20_score",
            "d60_score",
            "combined_score",
            "dominant_horizon",
            "behavior",
            "horizon_alignment",
            "dominance_strength",
        )
        if key in global_prediction
    }


def daily_report_to_dict(
    report: DailyReport,
    prediction: dict[str, Any] | None = None,
    blockers_count: dict[str, int] | None = None,
    asset_blockers: dict[str, list[str]] | None = None,
    update_status: dict[str, Any] | None = None,
    basket: dict[str, Any] | None = None,
    observation_candidates: list[dict[str, Any]] | None = None,
    position_actions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = _convert(asdict(report))
    raw["schema_version"] = "daily_report.v1"
    raw["runtime"] = artifact_metadata()
    global_prediction = _prediction_global(prediction)
    decision_prediction = _prediction_for_decision(prediction)

    if global_prediction:
        raw["prediction"] = global_prediction
        quality = global_prediction.get("model_quality", {})
        if isinstance(quality, dict):
            raw["model_quality"] = quality.get("status")
            raw["model_edge"] = quality.get("edge")
    else:
        raw["prediction"] = {}
        raw["model_quality"] = raw.get("model_quality", "")

    if blockers_count is not None:
        raw["blockers_count"] = dict(blockers_count)
        raw["blockers"] = dict(blockers_count)
    else:
        raw["blockers_count"] = {}
        raw["blockers"] = {}

    raw["decision"] = {
        "actionable": sum(
            1
            for decision in report.decisions
            if str(decision.permission.status.value).upper() == "READY"
        ),
        "watch": sum(
            1
            for decision in report.decisions
            if str(decision.permission.status.value).upper() == "WATCH"
        ),
        "blocked": sum(
            1
            for decision in report.decisions
            if str(decision.permission.status.value).upper() == "BLOCKED"
        ),
        "rejected": 0,
    }

    if update_status:
        raw["update_status"] = dict(update_status)
    else:
        raw["update_status"] = {}

    if basket is not None:
        raw["basket"] = dict(basket)
    else:
        raw["basket"] = {}

    if observation_candidates is not None:
        raw["observation_candidates"] = _convert(observation_candidates)
    else:
        raw["observation_candidates"] = []

    if position_actions is not None:
        converted_actions = _convert(position_actions)
        converted_actions.setdefault("schema_version", "position_actions.v1")
        raw["position_actions"] = converted_actions
        raw["exit_book"] = converted_actions.get("exit_book", {})
        raw["short_candidates"] = converted_actions.get("short_candidates", [])
        raw["hedge_candidates"] = converted_actions.get("hedge_candidates", [])
    else:
        raw["position_actions"] = {"schema_version": "position_actions.v1"}

    for index, decision in enumerate(report.decisions):
        ticker = decision.asset.ticker
        raw["decisions"][index]["decision_codes"] = list(decision_codes(decision))
        raw["decisions"][index]["decision_label"] = decision_label(decision)
        raw["decisions"][index]["blocker_reasons"] = list(
            (asset_blockers or {}).get(ticker, [])
        )
        if decision_prediction:
            raw["decisions"][index]["prediction"] = dict(decision_prediction)

    return raw


def render_daily_report_json(
    report: DailyReport,
    indent: int = 2,
    prediction: dict[str, Any] | None = None,
    blockers_count: dict[str, int] | None = None,
    asset_blockers: dict[str, list[str]] | None = None,
    update_status: dict[str, Any] | None = None,
    basket: dict[str, Any] | None = None,
    observation_candidates: list[dict[str, Any]] | None = None,
    position_actions: dict[str, Any] | None = None,
) -> str:
    payload = daily_report_to_dict(
        report,
        prediction=prediction,
        blockers_count=blockers_count,
        asset_blockers=asset_blockers,
        update_status=update_status,
        basket=basket,
        observation_candidates=observation_candidates,
        position_actions=position_actions,
    )
    return json.dumps(payload, ensure_ascii=False, indent=indent)


def write_daily_report_json(
    report: DailyReport,
    path: str | Path,
    prediction: dict[str, Any] | None = None,
    blockers_count: dict[str, int] | None = None,
    asset_blockers: dict[str, list[str]] | None = None,
    update_status: dict[str, Any] | None = None,
    basket: dict[str, Any] | None = None,
    observation_candidates: list[dict[str, Any]] | None = None,
    position_actions: dict[str, Any] | None = None,
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_daily_report_json(
            report,
            prediction=prediction,
            blockers_count=blockers_count,
            asset_blockers=asset_blockers,
            update_status=update_status,
            basket=basket,
            observation_candidates=observation_candidates,
            position_actions=position_actions,
        ),
        encoding="utf-8",
    )
