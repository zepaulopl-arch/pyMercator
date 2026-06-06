"""Build market context v2 from official/local sources."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from pymercator.context_engine.bcb import fetch_bcb_snapshot
from pymercator.context_engine.commodities import infer_oil_risk, load_commodities_snapshot
from pymercator.context_engine.copom import infer_copom_risk, load_copom_calendar
from pymercator.context_engine.earnings import infer_earnings_risk, load_earnings_calendar
from pymercator.context_engine.geopolitical import infer_geopolitical_risk, load_geopolitical_context
from pymercator.context_engine.inflation import fetch_focus_expectations, infer_inflation_bias
from pymercator.context_engine.sector_context import load_sector_context
from pymercator.context_engine.sources import SourceResult, read_json_file, write_json


DEFAULT_OUTPUT = "storage/context/latest_market_context.json"


def _source_status(results: dict[str, SourceResult]) -> dict[str, str]:
    return {name: result.status for name, result in results.items()}


def _overall_source_status(statuses: dict[str, str]) -> str:
    if not statuses:
        return "MISSING"
    ok_count = sum(1 for value in statuses.values() if value == "OK")
    if ok_count == len(statuses):
        return "OK"
    if ok_count == 0:
        return "MISSING"
    return "PARTIAL"


def _bcb_value(bcb_data: dict[str, Any], key: str) -> float | None:
    item = bcb_data.get(key)
    if isinstance(item, dict):
        value = item.get("value")
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _infer_rate_bias(selic: float | None, inflation_bias: str) -> str:
    if selic is None:
        return "UNKNOWN"
    if inflation_bias == "ABOVE_TARGET":
        return "TIGHT"
    if inflation_bias == "BELOW_TARGET":
        return "EASING_ROOM"
    return "HOLDING"


def _infer_market_trend(existing: dict[str, Any], inflation_bias: str, geopolitical_risk: str) -> str:
    existing_trend = existing.get("market_trend") or existing.get("trend")
    if existing_trend:
        return str(existing_trend).upper()
    if geopolitical_risk == "HIGH" or inflation_bias == "ABOVE_TARGET":
        return "CHOPPY"
    return "NEUTRAL"


def _infer_volatility(existing: dict[str, Any], oil_risk: str, geopolitical_risk: str) -> str:
    existing_vol = existing.get("market_volatility") or existing.get("volatility")
    if existing_vol:
        return str(existing_vol).upper()
    if oil_risk == "HIGH" or geopolitical_risk == "HIGH":
        return "HIGH"
    return "NORMAL"


def _score_context(
    inflation_bias: str,
    copom_risk: str,
    oil_risk: str,
    geopolitical_risk: str,
    earnings_risk: str,
) -> float:
    score = 55.0
    penalties = {
        "ABOVE_TARGET": 6.0,
        "HIGH": 7.0,
        "MEDIUM": 3.0,
    }
    if inflation_bias == "ABOVE_TARGET":
        score -= penalties["ABOVE_TARGET"]
    for risk in (copom_risk, oil_risk, geopolitical_risk, earnings_risk):
        if risk == "HIGH":
            score -= penalties["HIGH"]
        elif risk == "MEDIUM":
            score -= penalties["MEDIUM"]
    return round(max(0.0, min(100.0, score)), 1)


def build_market_context(
    *,
    output: str | Path = DEFAULT_OUTPUT,
    existing_context_path: str | Path = "storage/context/latest_market_context.json",
    use_network: bool = True,
    inflation_target: float = 3.0,
    copom_csv: str | Path = "data/context/copom_calendar.csv",
    commodities_csv: str | Path = "data/context/commodities.csv",
    earnings_csv: str | Path = "data/context/earnings_calendar.csv",
    geopolitical_json: str | Path = "data/context/geopolitical_context.json",
    sector_json: str | Path = "data/context/sector_context.json",
    write_output: bool = True,
) -> dict[str, Any]:
    """Build market context v2.

    Network sources are official BCB endpoints. Local files are explicit fallbacks.
    Missing sources are reported; they are not guessed.
    """
    existing_result = read_json_file(existing_context_path)
    existing = existing_result.data if isinstance(existing_result.data, dict) else {}

    if use_network:
        bcb = fetch_bcb_snapshot()
        focus = fetch_focus_expectations(reference_year=date.today().year)
    else:
        bcb = SourceResult(name="bcb_sgs", status="SKIPPED", data={})
        focus = SourceResult(name="bcb_focus", status="SKIPPED", data={})

    copom = load_copom_calendar(copom_csv)
    commodities = load_commodities_snapshot(commodities_csv)
    earnings = load_earnings_calendar(earnings_csv)
    geopolitical = load_geopolitical_context(geopolitical_json)
    sector = load_sector_context(sector_json)

    results = {
        "existing_context": existing_result,
        "bcb_sgs": bcb,
        "focus": focus,
        "copom": copom,
        "commodities": commodities,
        "earnings": earnings,
        "geopolitical": geopolitical,
        "sector": sector,
    }
    source_status = _source_status(results)

    bcb_data = bcb.data if isinstance(bcb.data, dict) else {}
    focus_data = focus.data if isinstance(focus.data, dict) else {}
    commodities_data = commodities.data if isinstance(commodities.data, dict) else {}
    earnings_data = earnings.data if isinstance(earnings.data, dict) else {}
    geopolitical_data = geopolitical.data if isinstance(geopolitical.data, dict) else {}
    sector_data = sector.data if isinstance(sector.data, dict) else {}

    selic = _bcb_value(bcb_data, "selic_target")
    ipca_monthly = _bcb_value(bcb_data, "ipca_monthly")
    inflation_expectation = focus_data.get("median") if focus.status == "OK" else None
    inflation_bias = infer_inflation_bias(inflation_expectation, inflation_target)
    selic_bias = _infer_rate_bias(selic, inflation_bias)

    next_copom = None
    if isinstance(copom.data, dict):
        next_copom = copom.data.get("next_meeting")
    copom_risk = infer_copom_risk(next_copom)

    oil_risk = infer_oil_risk(commodities_data)
    earnings_risk = infer_earnings_risk(earnings_data)
    geopolitical_risk = infer_geopolitical_risk(geopolitical_data)

    market_trend = _infer_market_trend(existing, inflation_bias, geopolitical_risk)
    market_volatility = _infer_volatility(existing, oil_risk, geopolitical_risk)
    context_score = _score_context(
        inflation_bias,
        copom_risk,
        oil_risk,
        geopolitical_risk,
        earnings_risk,
    )

    tags = []
    for label, value in (
        ("COPOM", copom_risk),
        ("OIL", oil_risk),
        ("GEO", geopolitical_risk),
        ("EARNINGS", earnings_risk),
        ("INFLATION", inflation_bias),
    ):
        if value not in {"UNKNOWN", "LOW", "ON_TARGET"}:
            tags.append(label)
    if not tags:
        tags.append("NEUTRAL")

    payload: dict[str, Any] = {
        "schema_version": "market_context.v2",
        "date": date.today().isoformat(),
        "market_trend": market_trend,
        "market_volatility": market_volatility,
        "context_score": context_score,
        "headline_tags": tags,
        "inflation": {
            "target": inflation_target,
            "ipca_monthly": ipca_monthly,
            "expectation": inflation_expectation,
            "bias": inflation_bias,
            "focus_reference_year": focus_data.get("reference_year"),
            "focus_date": focus_data.get("date"),
        },
        "rates": {
            "selic": selic,
            "selic_bias": selic_bias,
        },
        "copom": {
            "next_meeting": next_copom,
            "risk": copom_risk,
        },
        "commodities": {
            "items": commodities_data,
            "oil_risk": oil_risk,
        },
        "earnings": {
            "calendar": earnings_data,
            "risk": earnings_risk,
        },
        "geopolitical": {
            "items": geopolitical_data,
            "risk": geopolitical_risk,
        },
        "sector_context": sector_data,
        "source_status": source_status,
        "source_status_overall": _overall_source_status(source_status),
        "source_errors": {
            name: result.error
            for name, result in results.items()
            if result.error
        },
        "notes": "Generated by Aurum Context Engine. Missing sources are not inferred.",
    }

    if write_output:
        write_json(output, payload)
    return payload
