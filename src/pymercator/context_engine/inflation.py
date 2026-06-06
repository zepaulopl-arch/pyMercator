"""Inflation and Focus expectations sources."""

from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import quote

from pymercator.context_engine.sources import SourceResult, http_get_json, parse_float


FOCUS_BASE = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata"


def fetch_focus_expectations(
    indicator: str = "IPCA",
    reference_year: int | None = None,
    timeout: float = 12.0,
) -> SourceResult:
    """Fetch annual market expectations from BCB Olinda/Focus OData.

    The function is conservative. If the endpoint schema changes, it returns
    ERROR instead of inventing expectations.
    """
    year = int(reference_year or date.today().year)
    start = (date.today() - timedelta(days=45)).isoformat()
    filter_expr = (
        f"Indicador eq '{indicator}' and Data ge '{start}' "
        f"and DataReferencia eq '{year}'"
    )
    url = (
        f"{FOCUS_BASE}/ExpectativasMercadoAnuais?"
        f"$top=10&$orderby=Data desc&$filter={quote(filter_expr)}&$format=json"
    )
    result = http_get_json(url, timeout=timeout)
    result.name = "bcb_focus"
    if result.status != "OK":
        return result

    payload = result.data if isinstance(result.data, dict) else {}
    rows = payload.get("value", [])
    if not rows:
        result.status = "MISSING"
        result.data = {}
        result.error = "No Focus rows returned."
        return result

    row = rows[0]
    result.data = {
        "indicator": row.get("Indicador", indicator),
        "date": row.get("Data"),
        "reference_year": row.get("DataReferencia", year),
        "median": parse_float(row.get("Mediana")),
        "raw": row,
    }
    return result


def infer_inflation_bias(
    inflation_expectation: float | None,
    inflation_target: float | None,
    tolerance: float = 0.25,
) -> str:
    """Classify inflation expectation against target."""
    if inflation_expectation is None or inflation_target is None:
        return "UNKNOWN"
    if inflation_expectation > inflation_target + tolerance:
        return "ABOVE_TARGET"
    if inflation_expectation < inflation_target - tolerance:
        return "BELOW_TARGET"
    return "ON_TARGET"
