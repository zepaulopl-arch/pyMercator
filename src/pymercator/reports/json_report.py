from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

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
        "weights": prediction.get("weights", {}),
        "model_quality": prediction.get("model_quality", {}),
    }
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
        )
        if key in global_prediction
    }


def daily_report_to_dict(
    report: DailyReport,
    prediction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = _convert(asdict(report))
    global_prediction = _prediction_global(prediction)
    decision_prediction = _prediction_for_decision(prediction)

    if global_prediction:
        raw["prediction"] = global_prediction

    for index, decision in enumerate(report.decisions):
        raw["decisions"][index]["decision_codes"] = list(decision_codes(decision))
        raw["decisions"][index]["decision_label"] = decision_label(decision)
        if decision_prediction:
            raw["decisions"][index]["prediction"] = dict(decision_prediction)

    return raw


def render_daily_report_json(
    report: DailyReport,
    indent: int = 2,
    prediction: dict[str, Any] | None = None,
) -> str:
    payload = daily_report_to_dict(report, prediction=prediction)
    return json.dumps(payload, ensure_ascii=False, indent=indent)


def write_daily_report_json(
    report: DailyReport,
    path: str | Path,
    prediction: dict[str, Any] | None = None,
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_daily_report_json(report, prediction=prediction),
        encoding="utf-8",
    )
