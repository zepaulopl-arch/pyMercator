"""Shared source helpers for the Aurum context engine."""

from __future__ import annotations

import csv
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SourceResult:
    """Result returned by context sources."""

    name: str
    status: str
    data: Any = None
    url: str = ""
    error: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def as_status(self) -> str:
        return self.status


def http_get_json(url: str, timeout: float = 12.0) -> SourceResult:
    """Fetch JSON using stdlib only."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AurumContextEngine/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8-sig")
        return SourceResult(name="http", status="OK", data=json.loads(raw), url=url)
    except urllib.error.HTTPError as exc:
        return SourceResult(name="http", status="ERROR", url=url, error=f"HTTP {exc.code}: {exc.reason}")
    except urllib.error.URLError as exc:
        return SourceResult(name="http", status="ERROR", url=url, error=str(exc.reason))
    except TimeoutError:
        return SourceResult(name="http", status="ERROR", url=url, error="timeout")
    except Exception as exc:  # pragma: no cover - network/platform dependent
        return SourceResult(name="http", status="ERROR", url=url, error=str(exc))


def read_json_file(path: str | Path) -> SourceResult:
    p = Path(path)
    if not p.exists():
        return SourceResult(name=str(p), status="MISSING", data={})
    try:
        return SourceResult(
            name=str(p),
            status="OK",
            data=json.loads(p.read_text(encoding="utf-8-sig")),
        )
    except json.JSONDecodeError as exc:
        return SourceResult(name=str(p), status="INVALID_JSON", data={}, error=str(exc))
    except OSError as exc:
        return SourceResult(name=str(p), status="ERROR", data={}, error=str(exc))


def read_csv_file(path: str | Path) -> SourceResult:
    p = Path(path)
    if not p.exists():
        return SourceResult(name=str(p), status="MISSING", data=[])
    try:
        with p.open("r", encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        return SourceResult(name=str(p), status="OK", data=rows)
    except OSError as exc:
        return SourceResult(name=str(p), status="ERROR", data=[], error=str(exc))


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def first_non_empty(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return default


def parse_float(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default
