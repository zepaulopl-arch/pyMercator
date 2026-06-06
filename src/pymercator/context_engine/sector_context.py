"""Sector context local source."""

from __future__ import annotations

from pathlib import Path

from pymercator.context_engine.sources import SourceResult, read_json_file


DEFAULT_SECTOR_JSON = "data/context/sector_context.json"


def load_sector_context(path: str | Path = DEFAULT_SECTOR_JSON) -> SourceResult:
    result = read_json_file(path)
    result.name = "sector_context"
    if result.status == "OK" and not isinstance(result.data, dict):
        result.status = "INVALID_JSON"
        result.data = {}
    return result
