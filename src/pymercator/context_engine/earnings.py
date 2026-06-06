"""Earnings calendar local source.

File: data/context/earnings_calendar.csv

Schema:
date,ticker,event,risk,source
2026-06-10,PETR4,EARNINGS,MEDIUM,LOCAL
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from pymercator.context_engine.sources import SourceResult, read_csv_file


DEFAULT_EARNINGS_CSV = "data/context/earnings_calendar.csv"


def _parse_date(value: Any) -> date | None:
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except Exception:
        return None


def load_earnings_calendar(path: str | Path = DEFAULT_EARNINGS_CSV, window_days: int = 10) -> SourceResult:
    result = read_csv_file(path)
    result.name = "earnings"
    if result.status != "OK":
        return result

    today = date.today()
    items = []
    for row in result.data:
        event_date = _parse_date(row.get("date"))
        if not event_date:
            continue
        days = (event_date - today).days
        if 0 <= days <= window_days:
            items.append(
                {
                    "date": event_date.isoformat(),
                    "ticker": row.get("ticker", ""),
                    "event": row.get("event", "EARNINGS"),
                    "risk": str(row.get("risk", "MEDIUM") or "MEDIUM").upper(),
                    "source": row.get("source", "LOCAL"),
                    "days_to_event": days,
                }
            )
    result.data = {
        "window_days": window_days,
        "items": sorted(items, key=lambda item: (item["date"], item["ticker"])),
    }
    return result


def infer_earnings_risk(calendar: dict[str, Any]) -> str:
    items = calendar.get("items", []) if isinstance(calendar, dict) else []
    risks = {str(item.get("risk", "")).upper() for item in items}
    if "HIGH" in risks:
        return "HIGH"
    if "MEDIUM" in risks:
        return "MEDIUM"
    if items:
        return "LOW"
    return "UNKNOWN"
