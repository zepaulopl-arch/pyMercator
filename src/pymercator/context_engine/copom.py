"""COPOM calendar source.

Uses local CSV fallback because calendar endpoints may change and should not be
guessed. File: data/context/copom_calendar.csv

Schema:
date,event,source
2026-06-17,COPOM,LOCAL
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from pymercator.context_engine.sources import SourceResult, read_csv_file


DEFAULT_COPOM_CSV = "data/context/copom_calendar.csv"


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def load_copom_calendar(path: str | Path = DEFAULT_COPOM_CSV) -> SourceResult:
    result = read_csv_file(path)
    result.name = "copom_calendar"
    if result.status != "OK":
        return result

    today = date.today()
    events = []
    for row in result.data:
        event_date = _parse_date(row.get("date"))
        if event_date:
            events.append(
                {
                    "date": event_date.isoformat(),
                    "event": row.get("event", "COPOM"),
                    "source": row.get("source", "LOCAL"),
                    "days_to_event": (event_date - today).days,
                }
            )
    events.sort(key=lambda item: item["date"])
    next_events = [item for item in events if item["days_to_event"] >= 0]
    result.data = {
        "events": events,
        "next_meeting": next_events[0] if next_events else None,
    }
    return result


def infer_copom_risk(next_meeting: dict[str, Any] | None) -> str:
    if not next_meeting:
        return "UNKNOWN"
    days = next_meeting.get("days_to_event")
    if days is None:
        return "UNKNOWN"
    if days <= 3:
        return "HIGH"
    if days <= 10:
        return "MEDIUM"
    return "LOW"
