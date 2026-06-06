"""Geopolitical local context source."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pymercator.context_engine.sources import SourceResult, read_json_file


DEFAULT_GEOPOLITICAL_JSON = "data/context/geopolitical_context.json"


def load_geopolitical_context(path: str | Path = DEFAULT_GEOPOLITICAL_JSON) -> SourceResult:
    result = read_json_file(path)
    result.name = "geopolitical"
    if result.status == "OK" and not isinstance(result.data, dict):
        result.status = "INVALID_JSON"
        result.data = {}
    return result


def infer_geopolitical_risk(data: dict[str, Any]) -> str:
    for key in ("geopolitical_risk", "oil_war_risk", "war_risk", "risk"):
        value = data.get(key)
        if value:
            return str(value).upper()
    return "UNKNOWN"
