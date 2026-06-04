from __future__ import annotations

import csv
import json
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any

BORROW_POLICY_SCHEMA = "borrow_policy.v1"
DEFAULT_BORROW_DATA_PATH = "storage/borrow/latest_borrow_data.csv"
BORROW_COLUMNS = (
    "ticker",
    "borrow_available",
    "borrow_fee_pct",
    "recall_risk",
    "short_liquidity",
    "squeeze_risk",
    "updated_at",
)
DEFAULT_BORROW_POLICY: dict[str, Any] = {
    "schema_version": BORROW_POLICY_SCHEMA,
    "data_file": DEFAULT_BORROW_DATA_PATH,
    "freshness": {"max_age_days": 1, "stale_action": "BLOCK"},
    "defaults": {
        "missing_data_action": "DATA_MISSING",
        "execution_without_borrow_data": "BLOCK",
    },
}


def _ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def _to_float_or_none(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _to_float(value: Any, default: float = 0.0) -> float:
    parsed = _to_float_or_none(value)
    return default if parsed is None else parsed


def _to_bool_or_none(value: Any) -> bool | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in {"1", "true", "t", "yes", "y", "sim", "s", "available", "ok"}:
        return True
    if text in {"0", "false", "f", "no", "n", "nao", "unavailable"}:
        return False
    return None


def _risk_label(value: Any, *, default: str = "UNKNOWN") -> str:
    text = str(value or "").strip().upper()
    if not text:
        return default
    if text in {"LOW", "MEDIUM", "HIGH", "UNKNOWN"}:
        return text
    number = _to_float_or_none(text)
    if number is None:
        return default
    if number >= 70.0:
        return "HIGH"
    if number >= 40.0:
        return "MEDIUM"
    return "LOW"


def _liquidity_label(value: Any, *, default: str = "UNKNOWN") -> str:
    text = str(value or "").strip().upper()
    if not text:
        return default
    if text in {"OK", "WEAK", "UNKNOWN"}:
        return text
    parsed = _to_bool_or_none(text)
    if parsed is None:
        return default
    return "OK" if parsed else "WEAK"


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _age_days(value: Any, *, today: date | None = None) -> int | None:
    parsed = _parse_date(value)
    if parsed is None:
        return None
    current = today or date.today()
    return max(0, (current - parsed).days)


def load_borrow_policy(path: str | Path = "config/borrow_policy.json") -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        payload = dict(DEFAULT_BORROW_POLICY)
        payload["config_source"] = str(source)
        payload["config_status"] = "DEFAULT"
        return payload
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        merged = dict(DEFAULT_BORROW_POLICY)
        merged["config_source"] = str(source)
        merged["config_status"] = "DEFAULT"
        merged["config_warning"] = f"unable to load borrow policy: {exc}"
        return merged
    if not isinstance(payload, dict) or payload.get("schema_version") != BORROW_POLICY_SCHEMA:
        merged = dict(DEFAULT_BORROW_POLICY)
        merged["config_source"] = str(source)
        merged["config_status"] = "DEFAULT"
        merged["config_warning"] = "unsupported borrow policy schema"
        return merged
    merged = dict(DEFAULT_BORROW_POLICY)
    merged.update(payload)
    merged["freshness"] = {**DEFAULT_BORROW_POLICY["freshness"], **payload.get("freshness", {})}
    merged["defaults"] = {**DEFAULT_BORROW_POLICY["defaults"], **payload.get("defaults", {})}
    merged["config_source"] = str(source)
    merged["config_status"] = "OK"
    return merged


def normalize_borrow_row(row: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    ticker = _ticker(row.get("ticker"))
    errors: list[str] = []
    if not ticker:
        return None, ["missing ticker"]

    available = _to_bool_or_none(row.get("borrow_available"))
    if available is None:
        available = _to_bool_or_none(row.get("available"))
    available_qty = _to_float(row.get("available_qty"), 0.0)
    if available is None and available_qty > 0:
        available = True

    fee = _to_float_or_none(row.get("borrow_fee_pct"))
    if fee is None:
        fee = _to_float_or_none(row.get("borrow_cost_pct"))

    short_liquidity = _liquidity_label(row.get("short_liquidity"))
    if short_liquidity == "UNKNOWN":
        short_liquidity = _liquidity_label(row.get("liquidity_ok"))

    record = {
        "ticker": ticker,
        "borrow_available": available,
        "borrow_fee_pct": fee,
        "recall_risk": _risk_label(row.get("recall_risk")),
        "short_liquidity": short_liquidity,
        "squeeze_risk": _risk_label(row.get("squeeze_risk")),
        "updated_at": str(row.get("updated_at") or "").strip(),
        "available_qty": available_qty,
    }

    if available is None:
        errors.append(f"{ticker}: borrow_available missing or invalid")
    if fee is None:
        errors.append(f"{ticker}: borrow_fee_pct missing or invalid")
    return record, errors


def load_borrow_data(
    path: str | Path | None = None,
    *,
    policy_path: str | Path = "config/borrow_policy.json",
    today: date | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    policy = load_borrow_policy(policy_path)
    resolved = path if path not in {None, ""} else policy.get("data_file", DEFAULT_BORROW_DATA_PATH)
    source = Path(str(resolved))
    if not source.exists():
        return {
            "status": "MISSING",
            "path": str(source),
            "records": 0,
            "borrow_status": "BORROW_DATA_MISSING",
        }, {}

    records: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    try:
        with source.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                record, row_errors = normalize_borrow_row(row)
                errors.extend(row_errors)
                if record:
                    records[str(record["ticker"])] = record
    except Exception as exc:
        return {
            "status": "INVALID",
            "path": str(source),
            "records": 0,
            "warning": f"unable to load borrow data: {exc}",
            "borrow_status": "BORROW_DATA_INVALID",
        }, {}

    max_age = int(policy.get("freshness", {}).get("max_age_days", 1) or 1)
    stale_rows = sum(
        1
        for record in records.values()
        if (_age_days(record.get("updated_at"), today=today) is None)
        or (_age_days(record.get("updated_at"), today=today) or 0) > max_age
    )
    status = "OK"
    if not records:
        status = "DATA_MISSING"
    elif errors:
        status = "PARTIAL"
    elif stale_rows:
        status = "STALE"

    last_update = max(
        (str(record.get("updated_at") or "") for record in records.values()),
        default="",
    )
    return {
        "status": status,
        "path": str(source),
        "records": len(records),
        "last_update": last_update,
        "stale_rows": stale_rows,
        "errors": errors,
    }, records


def borrow_status_for_record(
    record: dict[str, Any] | None,
    *,
    thresholds: dict[str, Any],
    policy: dict[str, Any],
    today: date | None = None,
) -> tuple[str, str]:
    borrow_thresholds = thresholds.get("borrow", {}) if isinstance(thresholds, dict) else {}
    if not record:
        return "BORROW_DATA_MISSING", "borrow/cost unavailable"

    max_age = int(policy.get("freshness", {}).get("max_age_days", 1) or 1)
    age = _age_days(record.get("updated_at"), today=today)
    if age is None or age > max_age:
        return "BORROW_STALE", "borrow data stale"
    if record.get("borrow_available") is False:
        return "BORROW_UNAVAILABLE", "borrow unavailable"
    if record.get("borrow_available") is None:
        return "BORROW_DATA_MISSING", "borrow availability unknown"

    fee = record.get("borrow_fee_pct")
    max_fee = _to_float(borrow_thresholds.get("max_borrow_fee_pct"), 5.0)
    if fee is None:
        if bool(borrow_thresholds.get("block_if_cost_unknown", True)):
            return "BORROW_DATA_MISSING", "borrow cost unavailable"
    elif float(fee) > max_fee:
        return "BORROW_COST_HIGH", "borrow cost above limit"

    if str(record.get("recall_risk", "UNKNOWN")).upper() == "HIGH":
        return "BORROW_RECALL_RISK", "recall risk high"
    if str(record.get("short_liquidity", "UNKNOWN")).upper() != "OK":
        return "BORROW_LIQUIDITY_WEAK", "short liquidity not confirmed"
    if str(record.get("squeeze_risk", "UNKNOWN")).upper() == "HIGH":
        return "BORROW_SQUEEZE_HIGH", "squeeze risk high"
    return "BORROW_OK", "borrow available"


def evaluate_borrow_record(
    record: dict[str, Any] | None,
    config: dict[str, Any],
) -> tuple[bool, str]:
    thresholds = {
        "borrow": {
            "max_borrow_fee_pct": config.get(
                "max_borrow_fee_pct",
                config.get("max_borrow_cost_pct", 5.0),
            ),
            "block_if_cost_unknown": True,
        }
    }
    policy = {"freshness": {"max_age_days": 999999}}
    status, reason = borrow_status_for_record(record, thresholds=thresholds, policy=policy)
    return status == "BORROW_OK", reason


def validate_borrow_csv(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {
            "status": "FAIL",
            "path": str(source),
            "valid": False,
            "rows": 0,
            "errors": [f"borrow file not found: {source}"],
        }
    errors: list[str] = []
    rows = 0
    with source.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fields = set(reader.fieldnames or [])
        if "ticker" not in fields:
            errors.append("missing required column: ticker")
        has_new_schema = set(BORROW_COLUMNS).issubset(fields)
        has_legacy_schema = {"ticker", "available", "borrow_cost_pct"}.issubset(fields)
        if not has_new_schema and not has_legacy_schema:
            errors.append("missing borrow columns")
        for row in reader:
            rows += 1
            _record, row_errors = normalize_borrow_row(row)
            errors.extend(row_errors)
    return {
        "status": "OK" if not errors else "FAIL",
        "path": str(source),
        "valid": not errors,
        "rows": rows,
        "errors": errors,
    }


def import_borrow_file(
    source: str | Path,
    *,
    output: str | Path | None = None,
    policy_path: str | Path = "config/borrow_policy.json",
) -> dict[str, Any]:
    validation = validate_borrow_csv(source)
    if not validation["valid"]:
        return {
            "command": "borrow import",
            "status": "FAIL",
            "source": str(source),
            "output": str(output or ""),
            "rows": validation["rows"],
            "errors": validation["errors"],
        }
    policy = load_borrow_policy(policy_path)
    destination = Path(str(output or policy.get("data_file", DEFAULT_BORROW_DATA_PATH)))
    destination.parent.mkdir(parents=True, exist_ok=True)
    if Path(source).resolve() != destination.resolve():
        shutil.copy2(source, destination)
    return {
        "command": "borrow import",
        "status": "OK",
        "source": str(source),
        "output": str(destination),
        "rows": validation["rows"],
        "errors": [],
    }


def _read_expected_tickers(path: str | Path) -> set[str]:
    source = Path(path)
    if not source.exists():
        return set()
    with source.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return {_ticker(row.get("ticker")) for row in reader if _ticker(row.get("ticker"))}


def diagnose_borrow_data(
    *,
    path: str | Path | None = None,
    tickers_file: str | Path = "data/universes/ibov_live.csv",
    policy_path: str | Path = "config/borrow_policy.json",
    thresholds: dict[str, Any] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    status, records = load_borrow_data(path, policy_path=policy_path, today=today)
    policy = load_borrow_policy(policy_path)
    thresholds = thresholds or {"borrow": {"max_borrow_fee_pct": 5.0}}
    expected = _read_expected_tickers(tickers_file)
    missing = sorted(expected - set(records)) if expected else []
    unavailable = 0
    high_cost = 0
    stale = 0
    invalid = len(status.get("errors", []) or [])
    rows: list[dict[str, Any]] = []
    for record in records.values():
        borrow_status, reason = borrow_status_for_record(
            record,
            thresholds=thresholds,
            policy=policy,
            today=today,
        )
        if borrow_status == "BORROW_UNAVAILABLE":
            unavailable += 1
        if borrow_status == "BORROW_COST_HIGH":
            high_cost += 1
        if borrow_status == "BORROW_STALE":
            stale += 1
        rows.append({**record, "borrow_status": borrow_status, "reason": reason})
    return {
        "command": "borrow diagnose",
        "file": status.get("path", str(path or policy.get("data_file", DEFAULT_BORROW_DATA_PATH))),
        "status": status.get("status", "UNKNOWN"),
        "rows": len(records),
        "last_update": status.get("last_update", ""),
        "stale_rows": stale,
        "unavailable": unavailable,
        "high_cost": high_cost,
        "invalid_rows": invalid,
        "missing_tickers": len(missing),
        "missing_ticker_list": missing,
        "records": rows,
        "errors": status.get("errors", []),
    }


def render_borrow_show(status: dict[str, Any], records: dict[str, dict[str, Any]]) -> str:
    lines = [
        "BORROW DATA",
        "-" * 80,
        f"file                 {status.get('path', '-')}",
        f"status               {status.get('status', '-')}",
        f"rows                 {len(records)}",
    ]
    if not records:
        lines.append("reason               no borrow rows loaded")
        return "\n".join(lines)
    lines.extend(
        [
            "",
            f"{'TICKER':<8} {'AVAIL':<7} {'FEE%':>7} {'RECALL':<8} {'LIQ':<7} {'SQUEEZE':<8} UPDATED",
        ]
    )
    for ticker, record in sorted(records.items()):
        fee = record.get("borrow_fee_pct")
        fee_text = "-" if fee is None else f"{float(fee):>7.2f}"
        avail = record.get("borrow_available")
        avail_text = "-" if avail is None else str(bool(avail)).upper()
        lines.append(
            f"{ticker:<8} {avail_text:<7} {fee_text} "
            f"{str(record.get('recall_risk', '-')):<8} "
            f"{str(record.get('short_liquidity', '-')):<7} "
            f"{str(record.get('squeeze_risk', '-')):<8} "
            f"{record.get('updated_at', '-') or '-'}"
        )
    return "\n".join(lines)


def render_borrow_diagnose(payload: dict[str, Any]) -> str:
    lines = [
        "BORROW DIAGNOSE",
        "-" * 80,
        f"file                 {payload.get('file', '-')}",
        f"status               {payload.get('status', '-')}",
        f"rows                 {payload.get('rows', 0)}",
        f"last_update          {payload.get('last_update', '-') or '-'}",
        f"stale_rows           {payload.get('stale_rows', 0)}",
        f"unavailable          {payload.get('unavailable', 0)}",
        f"high_cost            {payload.get('high_cost', 0)}",
        f"missing_tickers      {payload.get('missing_tickers', 0)}",
    ]
    if payload.get("errors"):
        lines.extend(["", "ERRORS", "-" * 80])
        for error in payload.get("errors", []):
            lines.append(f"- {error}")
    return "\n".join(lines)
