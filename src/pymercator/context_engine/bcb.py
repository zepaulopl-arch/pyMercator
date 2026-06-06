"""Banco Central do Brasil sources.

Uses the SGS public time-series endpoint:
https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados/ultimos/{n}?formato=json
"""

from __future__ import annotations

from typing import Any

from pymercator.context_engine.sources import SourceResult, http_get_json, parse_float


SGS_DEFAULT_SERIES = {
    # These are intentionally configurable in builder/CLI in future stages.
    # Common BCB SGS series:
    # 432 = Selic target defined by Copom.
    # 433 = IPCA monthly variation.
    "selic_target": 432,
    "ipca_monthly": 433,
}


def fetch_bcb_series(series_code: int, limit: int = 1, timeout: float = 12.0) -> SourceResult:
    """Fetch latest values for a SGS series."""
    url = (
        "https://api.bcb.gov.br/dados/serie/bcdata.sgs."
        f"{int(series_code)}/dados/ultimos/{int(limit)}?formato=json"
    )
    result = http_get_json(url, timeout=timeout)
    result.name = f"bcb_sgs_{series_code}"
    if result.status != "OK":
        return result
    rows = result.data if isinstance(result.data, list) else []
    parsed = []
    for row in rows:
        parsed.append(
            {
                "date": row.get("data"),
                "value": parse_float(row.get("valor")),
                "raw": row,
            }
        )
    result.data = parsed
    result.detail["series_code"] = int(series_code)
    return result


def fetch_bcb_snapshot(timeout: float = 12.0) -> SourceResult:
    """Fetch default BCB macro snapshot."""
    values: dict[str, Any] = {}
    source_status: dict[str, str] = {}
    errors: dict[str, str] = {}

    for name, code in SGS_DEFAULT_SERIES.items():
        item = fetch_bcb_series(code, limit=1, timeout=timeout)
        source_status[name] = item.status
        if item.status == "OK" and item.data:
            values[name] = item.data[-1]
        elif item.error:
            errors[name] = item.error

    status = "OK" if all(value == "OK" for value in source_status.values()) else "PARTIAL"
    if all(value != "OK" for value in source_status.values()):
        status = "ERROR"

    return SourceResult(
        name="bcb_sgs",
        status=status,
        data=values,
        detail={"source_status": source_status, "errors": errors},
    )
