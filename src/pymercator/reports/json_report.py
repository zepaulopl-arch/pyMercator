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


def daily_report_to_dict(report: DailyReport) -> dict[str, Any]:
    raw = _convert(asdict(report))

    for index, decision in enumerate(report.decisions):
        raw["decisions"][index]["decision_codes"] = list(decision_codes(decision))
        raw["decisions"][index]["decision_label"] = decision_label(decision)

    return raw


def render_daily_report_json(report: DailyReport, indent: int = 2) -> str:
    payload = daily_report_to_dict(report)
    return json.dumps(payload, ensure_ascii=False, indent=indent)


def write_daily_report_json(report: DailyReport, path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_daily_report_json(report),
        encoding="utf-8",
    )
