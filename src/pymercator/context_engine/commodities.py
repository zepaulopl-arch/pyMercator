"""Commodities local source.

File: data/context/commodities.csv

Schema:
name,value,change_pct,risk,source,updated_at
oil,82.1,1.4,HIGH,LOCAL,2026-06-06
iron_ore,105.0,-0.5,MEDIUM,LOCAL,2026-06-06
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pymercator.context_engine.sources import SourceResult, parse_float, read_csv_file


DEFAULT_COMMODITIES_CSV = "data/context/commodities.csv"


def load_commodities_snapshot(path: str | Path = DEFAULT_COMMODITIES_CSV) -> SourceResult:
    result = read_csv_file(path)
    result.name = "commodities"
    if result.status != "OK":
        return result

    data: dict[str, Any] = {}
    for row in result.data:
        name = str(row.get("name", "")).strip().lower()
        if not name:
            continue
        data[name] = {
            "value": parse_float(row.get("value")),
            "change_pct": parse_float(row.get("change_pct")),
            "risk": str(row.get("risk", "UNKNOWN") or "UNKNOWN").upper(),
            "source": row.get("source", "LOCAL"),
            "updated_at": row.get("updated_at", ""),
        }
    result.data = data
    return result


def infer_oil_risk(commodities: dict[str, Any]) -> str:
    for key in ("oil", "brent", "wti"):
        item = commodities.get(key)
        if isinstance(item, dict) and item.get("risk"):
            return str(item["risk"]).upper()
    return "UNKNOWN"
