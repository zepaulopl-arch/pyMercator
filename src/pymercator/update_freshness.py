from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _staleness_days(value: Any, *, today: date) -> int | None:
    parsed = _parse_date(value)
    if parsed is None:
        return None
    return max(0, (today - parsed).days)


def _status_for_staleness(days: int | None) -> str:
    if days is None:
        return "UNKNOWN"
    if days <= 3:
        return "OK"
    if days <= 7:
        return "WARNING"
    return "FAIL"


def _ticker_from_path(path: Any) -> str:
    stem = Path(str(path or "")).stem.upper()
    if stem.endswith(".SA"):
        stem = stem[:-3]
    return stem or "-"


def _index_required_map(steps: list[dict[str, Any]]) -> dict[str, bool]:
    for step in steps:
        if step.get("step") != "indices":
            continue
        payload = step.get("payload", {})
        if not isinstance(payload, dict):
            continue
        mapping: dict[str, bool] = {}
        for item in payload.get("results", []) or []:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or _ticker_from_path(item.get("path"))).upper()
            mapping[symbol] = bool(item.get("required", True))
            path_symbol = _ticker_from_path(item.get("path"))
            if path_symbol != "-":
                mapping[path_symbol] = bool(item.get("required", True))
        return mapping
    return {}


def _items_from_check_step(
    steps: list[dict[str, Any]],
    name: str,
    *,
    today: date,
    required_map: dict[str, bool] | None = None,
) -> dict[str, dict[str, Any]]:
    required_map = required_map or {}
    for step in steps:
        if step.get("step") != name:
            continue
        payload = step.get("payload", {})
        if not isinstance(payload, dict):
            continue
        results = payload.get("results", []) or []
        items: dict[str, dict[str, Any]] = {}
        for result in results:
            if not isinstance(result, dict):
                continue
            key = _ticker_from_path(result.get("path"))
            last_date = result.get("end_date")
            days = _staleness_days(last_date, today=today)
            status = _status_for_staleness(days)
            item: dict[str, Any] = {
                "last_date": last_date or "",
                "staleness_days": days if days is not None else None,
                "status": status,
            }
            if required_map:
                item["required"] = bool(required_map.get(key, required_map.get(key.upper(), True)))
            items[key] = item
        return items
    return {}


def _latest_date(items: dict[str, dict[str, Any]]) -> str:
    dates = [
        str(item.get("last_date") or "")
        for item in items.values()
        if str(item.get("last_date") or "")
    ]
    return max(dates) if dates else ""


def _max_staleness(items: dict[str, dict[str, Any]]) -> int:
    values = [
        int(item["staleness_days"])
        for item in items.values()
        if item.get("staleness_days") is not None
    ]
    return max(values) if values else 0


def _stale_count(items: dict[str, dict[str, Any]]) -> int:
    return sum(1 for item in items.values() if str(item.get("status")) in {"WARNING", "FAIL"})


def build_data_freshness(
    steps: list[dict[str, Any]],
    *,
    today: date | None = None,
) -> dict[str, Any]:
    current_date = today or date.today()
    required_map = _index_required_map(steps)
    assets = _items_from_check_step(steps, "prices_check", today=current_date)
    indices = _items_from_check_step(
        steps,
        "indices_check",
        today=current_date,
        required_map=required_map,
    )

    max_staleness = max(_max_staleness(assets), _max_staleness(indices))
    stale_assets = _stale_count(assets)
    stale_indices = _stale_count(indices)
    required_stale_indices = sum(
        1
        for item in indices.values()
        if item.get("required", True) and str(item.get("status")) in {"WARNING", "FAIL"}
    )

    total_assets = len(assets)
    price_fail_ratio = (stale_assets / total_assets) if total_assets else 0.0
    if required_stale_indices or price_fail_ratio > 0.5:
        freshness_status = "FAIL"
    elif max_staleness > 3 or stale_assets or stale_indices:
        freshness_status = "WARNING"
    else:
        freshness_status = "OK"

    penalty = (
        min(max_staleness * 3.0, 45.0)
        + stale_assets * 1.0
        + stale_indices * 5.0
        + required_stale_indices * 20.0
    )
    data_quality_score = round(max(0.0, 100.0 - penalty), 1)

    return {
        "prices_last_date": _latest_date(assets),
        "indices_last_date": _latest_date(indices),
        "max_staleness_days": max_staleness,
        "stale_assets": stale_assets,
        "stale_indices": stale_indices,
        "freshness_status": freshness_status,
        "data_quality_score": data_quality_score,
        "assets": assets,
        "indices": indices,
    }
