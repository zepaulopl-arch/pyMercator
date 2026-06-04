from __future__ import annotations

import base64
import csv
import json
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from io import StringIO
from pathlib import Path
from typing import Any

SOURCE_ORDER = ("auto", "market", "bcb", "b3", "cvm", "manual")
SOURCE_LABELS = {
    "auto": "AUTO",
    "market": "MARKET",
    "bcb": "BCB",
    "b3": "B3",
    "cvm": "CVM",
    "manual": "MANUAL",
    "thresholds": "THR",
}
VALID_SOURCE_STATUSES = {"OK", "PARTIAL", "FAIL", "NOT_IMPLEMENTED", "DISABLED"}

BCB_SERIES = {
    "selic_target": 432,
    "ipca_monthly": 433,
    "usdbrl_ptax_sell": 1,
}
B3_IBOV_PORTFOLIO_URL = (
    "https://sistemaswebb3-listados.b3.com.br/"
    "indexProxy/indexCall/GetPortfolioDay/{payload}?language=pt-br"
)
CVM_CIA_ABERTA_CAD_URL = (
    "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
)


def _utc_now_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _date_from_any(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "T" in text:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return text[:10]
    if "/" in text:
        for fmt in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                pass
    return text[:10]


def _date_from_http(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return ""
    return parsed.date().isoformat()


def normalize_source_status(value: Any) -> str:
    status = str(value or "").strip().upper()
    if status in {"NOT_IMPL", "NOT IMPLEMENTED"}:
        return "NOT_IMPLEMENTED"
    if status in VALID_SOURCE_STATUSES:
        return status
    if status == "UNKNOWN":
        return "FAIL"
    return "FAIL"


def source_diag(
    source: str,
    *,
    status: str,
    last_update: str = "",
    items: int = 0,
    error: str = "",
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    key = source.lower()
    return {
        "source": SOURCE_LABELS.get(key, key.upper()),
        "status": normalize_source_status(status),
        "last_update": _date_from_any(last_update) or "",
        "items": int(items or 0),
        "error": str(error or ""),
        "detail": detail or {},
    }


def _enabled(config: dict[str, Any], source: str) -> bool:
    sources = config.get("sources", {}) if isinstance(config, dict) else {}
    return bool(sources.get(source, True))


def _items_from_values(values: list[Any] | dict[str, Any] | None) -> int:
    if isinstance(values, dict):
        return sum(1 for value in values.values() if value not in (None, "", []))
    if isinstance(values, list):
        return len(values)
    return 0


def base_source_diagnostics(
    *,
    auto_context: dict[str, Any],
    metrics: dict[str, Any],
    manual_status: str,
    manual: dict[str, Any],
    thresholds_status: str,
    config: dict[str, Any],
    external_diagnostics: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    external_diagnostics = external_diagnostics or {}
    generated_at = (
        auto_context.get("generated_at")
        or auto_context.get("data_date")
        or auto_context.get("updated_at")
        or _utc_now_date()
    )
    diagnostics: dict[str, dict[str, Any]] = {
        "auto": source_diag(
            "auto",
            status="OK" if auto_context else "FAIL",
            last_update=generated_at if auto_context else "",
            items=_items_from_values(auto_context.get("headline_tags", []))
            + _items_from_values(metrics),
            error="" if auto_context else "auto context not available",
        ),
        "thresholds": source_diag(
            "thresholds",
            status=thresholds_status,
            last_update=_utc_now_date(),
            items=1,
            error="" if thresholds_status == "OK" else "threshold schema mismatch",
        ),
        "market": source_diag(
            "market",
            status="OK" if auto_context else "FAIL",
            last_update=generated_at if auto_context else "",
            items=_items_from_values(metrics),
            error="" if auto_context else "market data context not available",
        ),
        "manual": source_diag(
            "manual",
            status=manual_status,
            last_update=_utc_now_date() if manual_status == "OK" else "",
            items=_items_from_values(manual.get("headline_tags", []))
            + (1 if manual.get("notes") else 0),
            error="" if manual_status == "OK" else "manual context not provided",
        ),
    }

    for source in ("bcb", "b3", "cvm"):
        if not _enabled(config, source):
            diagnostics[source] = source_diag(
                source,
                status="DISABLED",
                error="source disabled in config/market_context.json",
            )
        else:
            diagnostics[source] = source_diag(
                source,
                status="FAIL",
                error="source not refreshed in this run",
            )

    for source, diagnostic in external_diagnostics.items():
        key = str(source).lower()
        if key in diagnostics:
            diagnostics[key] = normalize_diagnostic(key, diagnostic)

    return diagnostics


def normalize_diagnostic(source: str, diagnostic: dict[str, Any]) -> dict[str, Any]:
    key = source.lower()
    return source_diag(
        key,
        status=diagnostic.get("status", "FAIL"),
        last_update=str(diagnostic.get("last_update", "") or ""),
        items=int(diagnostic.get("items", 0) or 0),
        error=str(diagnostic.get("error", "") or ""),
        detail=diagnostic.get("detail", {}) if isinstance(diagnostic.get("detail"), dict) else {},
    )


def diagnostics_from_context(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = context.get("source_diagnostics", {})
    diagnostics: dict[str, dict[str, Any]] = {}
    if isinstance(raw, dict):
        for source, item in raw.items():
            if isinstance(item, dict):
                diagnostics[str(source).lower()] = normalize_diagnostic(str(source), item)
    elif isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source", "")).lower()
            reverse = {value.lower(): key for key, value in SOURCE_LABELS.items()}
            source = reverse.get(source, source)
            if source:
                diagnostics[source] = normalize_diagnostic(source, item)

    context_sources = context.get("context_sources", {})
    if isinstance(context_sources, dict):
        for source, status in context_sources.items():
            key = str(source).lower()
            if key not in diagnostics and key in set(SOURCE_ORDER) | {"thresholds"}:
                diagnostics[key] = source_diag(
                    key,
                    status=normalize_source_status(status),
                    error=(
                        "legacy UNKNOWN status; refresh required"
                        if str(status).upper() == "UNKNOWN"
                        else ""
                    ),
                )

    return diagnostics


def ordered_diagnostics(
    diagnostics: dict[str, dict[str, Any]],
    *,
    include_thresholds: bool = False,
) -> list[dict[str, Any]]:
    order = list(SOURCE_ORDER)
    if include_thresholds:
        order.insert(2, "thresholds")
    rows = [
        diagnostics[source]
        for source in order
        if source in diagnostics
    ]
    seen = set(order)
    rows.extend(
        normalize_diagnostic(source, item)
        for source, item in sorted(diagnostics.items())
        if source not in seen and (include_thresholds or source != "thresholds")
    )
    return rows


def render_source_diagnostics(
    diagnostics: dict[str, dict[str, Any]],
    *,
    title: str = "CONTEXT SOURCES",
    include_thresholds: bool = False,
) -> str:
    lines = [
        title,
        "-" * 80,
        f"{'SOURCE':<8} {'STATUS':<16} {'LAST_UPDATE':<12} {'ITEMS':>5}   ERROR",
    ]
    for item in ordered_diagnostics(diagnostics, include_thresholds=include_thresholds):
        error = str(item.get("error") or "-")
        last_update = str(item.get("last_update") or "-")
        lines.append(
            f"{item.get('source', '-'):<8} "
            f"{item.get('status', '-'):<16} "
            f"{last_update:<12} "
            f"{int(item.get('items', 0) or 0):>5}   "
            f"{error}"
        )
    return "\n".join(lines)


def _fetch_json(url: str, *, timeout: int = 10) -> tuple[dict[str, Any] | list[Any], dict[str, str]]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "pyMercator/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
        headers = {key: value for key, value in response.headers.items()}
    return payload, headers


def _fetch_text(url: str, *, timeout: int = 10, encoding: str = "utf-8") -> tuple[str, dict[str, str]]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "pyMercator/1.0",
            "Accept": "text/csv,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        headers = {key: value for key, value in response.headers.items()}
    return body.decode(encoding, errors="replace"), headers


def fetch_bcb_context_source(*, timeout: int = 10) -> tuple[dict[str, Any], dict[str, Any]]:
    series: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for name, code in BCB_SERIES.items():
        url = (
            "https://api.bcb.gov.br/dados/serie/"
            f"bcdata.sgs.{code}/dados/ultimos/1?formato=json"
        )
        try:
            payload, _headers = _fetch_json(url, timeout=timeout)
            if not isinstance(payload, list) or not payload:
                raise ValueError("empty SGS response")
            item = payload[-1]
            last_update = _date_from_any(item.get("data"))
            value = float(str(item.get("valor", "0")).replace(",", "."))
            series[name] = {
                "code": code,
                "value": value,
                "last_update": last_update,
                "source": f"BCB_SGS_{code}",
            }
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    status = "OK" if len(series) == len(BCB_SERIES) else "PARTIAL" if series else "FAIL"
    last_update = max(
        (item["last_update"] for item in series.values() if item.get("last_update")),
        default="",
    )
    diagnostic = source_diag(
        "bcb",
        status=status,
        last_update=last_update,
        items=len(series),
        error="; ".join(errors),
        detail={"series": list(series)},
    )
    data = {
        "macro": {
            "selic": {
                "current": series.get("selic_target", {}).get("value"),
                "source": series.get("selic_target", {}).get("source", "BCB_SGS_432"),
                "last_update": series.get("selic_target", {}).get("last_update"),
            },
            "ipca": {
                "monthly": series.get("ipca_monthly", {}).get("value"),
                "source": series.get("ipca_monthly", {}).get("source", "BCB_SGS_433"),
                "last_update": series.get("ipca_monthly", {}).get("last_update"),
            },
            "usdbrl_ptax": {
                "last": series.get("usdbrl_ptax_sell", {}).get("value"),
                "source": series.get("usdbrl_ptax_sell", {}).get("source", "BCB_SGS_1"),
                "last_update": series.get("usdbrl_ptax_sell", {}).get("last_update"),
            },
        }
    }
    return diagnostic, data


def fetch_b3_context_source(*, timeout: int = 10) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = {
        "language": "pt-br",
        "pageNumber": 1,
        "pageSize": 120,
        "index": "IBOV",
    }
    encoded = base64.b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    url = B3_IBOV_PORTFOLIO_URL.format(payload=encoded)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 pyMercator/1.0",
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://sistemaswebb3-listados.b3.com.br/indexPage/day/IBOV?language=pt-br",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    if not raw.strip():
        raise ValueError("empty B3 portfolio response")
    payload = json.loads(raw)
    results = payload.get("results", [])
    if not isinstance(results, list) or not results:
        raise ValueError("B3 portfolio response has no results")
    header = payload.get("header", {}) if isinstance(payload.get("header"), dict) else {}
    last_update = _date_from_any(header.get("date"))
    top = [
        {
            "ticker": str(row.get("cod", "")).strip(),
            "weight": str(row.get("part", "")).strip(),
        }
        for row in results[:10]
        if isinstance(row, dict)
    ]
    diagnostic = source_diag(
        "b3",
        status="OK",
        last_update=last_update,
        items=len(results),
        detail={"index": "IBOV", "endpoint": "GetPortfolioDay"},
    )
    data = {
        "equity_indices": {
            "ibov": {
                "source": "B3_GET_PORTFOLIO_DAY",
                "last_update": last_update,
                "constituents": len(results),
                "top_constituents": top,
            }
        }
    }
    return diagnostic, data


def fetch_cvm_context_source(*, timeout: int = 10) -> tuple[dict[str, Any], dict[str, Any]]:
    text, headers = _fetch_text(CVM_CIA_ABERTA_CAD_URL, timeout=timeout, encoding="iso-8859-1")
    reader = csv.DictReader(StringIO(text), delimiter=";")
    rows = [row for row in reader]
    if not rows:
        raise ValueError("empty CVM cia aberta cadastro response")
    active = sum(1 for row in rows if str(row.get("SIT", "")).strip().upper() == "ATIVO")
    last_update = _date_from_http(headers.get("Last-Modified")) or _utc_now_date()
    diagnostic = source_diag(
        "cvm",
        status="OK",
        last_update=last_update,
        items=len(rows),
        detail={"dataset": "cia_aberta_cad", "active_companies": active},
    )
    data = {
        "corporate_calendar": {
            "source": "CVM_DADOS_ABERTOS_CIA_ABERTA_CAD",
            "last_update": last_update,
            "companies": len(rows),
            "active_companies": active,
        }
    }
    return diagnostic, data


def collect_external_source(
    source: str,
    *,
    timeout: int = 10,
) -> tuple[dict[str, Any], dict[str, Any]]:
    key = source.lower()
    try:
        if key == "bcb":
            return fetch_bcb_context_source(timeout=timeout)
        if key == "b3":
            return fetch_b3_context_source(timeout=timeout)
        if key == "cvm":
            return fetch_cvm_context_source(timeout=timeout)
        return (
            source_diag(
                key,
                status="NOT_IMPLEMENTED",
                error="connector not implemented",
            ),
            {},
        )
    except Exception as exc:
        return source_diag(key, status="FAIL", error=str(exc)), {}


def collect_market_context_sources(
    *,
    config: dict[str, Any],
    sources: list[str] | None = None,
    timeout: int = 10,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    requested = [source.lower() for source in (sources or ["bcb", "b3", "cvm"])]
    diagnostics: dict[str, dict[str, Any]] = {}
    source_data: dict[str, Any] = {}
    for source in requested:
        if not _enabled(config, source):
            diagnostics[source] = source_diag(
                source,
                status="DISABLED",
                error="source disabled in config/market_context.json",
            )
            continue
        diagnostic, data = collect_external_source(source, timeout=timeout)
        diagnostics[source] = diagnostic
        if data:
            source_data[source] = data
    return diagnostics, source_data


def merge_source_data(target: dict[str, Any], source_data: dict[str, Any]) -> None:
    for data in source_data.values():
        if not isinstance(data, dict):
            continue
        macro = data.get("macro")
        if isinstance(macro, dict):
            target.setdefault("macro", {}).update(
                {
                    key: value
                    for key, value in macro.items()
                    if isinstance(value, dict) and any(v is not None for v in value.values())
                }
            )
        equity = data.get("equity_indices")
        if isinstance(equity, dict):
            target.setdefault("equity_indices", {})
            for key, value in equity.items():
                if isinstance(value, dict):
                    target["equity_indices"].setdefault(key, {}).update(value)
        calendar = data.get("corporate_calendar")
        if isinstance(calendar, dict):
            target.setdefault("corporate_calendar", {}).update(calendar)


def read_json_file(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
