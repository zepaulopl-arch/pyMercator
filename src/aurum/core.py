from __future__ import annotations

import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


TABLE_KEYS = ("real_long", "real_short", "obs_long", "obs_short")
DEFAULT_TABLE_LIMIT = 10
DEFAULT_REVIEW_LIMIT = 10
TABLE_TITLES = {
    "real_long": "REAL LONG",
    "real_short": "REAL SHORT",
    "obs_long": "OBS LONG",
    "obs_short": "OBS SHORT",
}
REVIEW_TITLES = {
    "real_long": "REAL LONG REVIEW",
    "real_short": "REAL SHORT REVIEW",
    "obs_long": "OBS LONG REVIEW",
    "obs_short": "OBS SHORT REVIEW",
}
LONG_READY_STATUSES = {"READY", "EXEC_READY", "LONG_READY", "BUY_READY"}
SHORT_READY_STATUSES = {"READY", "EXEC_READY", "SHORT_READY", "SHORT_EXEC_READY"}


def _today() -> str:
    return date.today().isoformat()


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _as_text(value: Any, default: str = "") -> str:
    text = "" if value is None else str(value).strip()
    return text or default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "sim"}


def _clean_ticker(value: Any) -> str:
    ticker = _as_text(value).upper()
    return ticker[:-3] if ticker.endswith(".SA") else ticker


def _nested(row: dict[str, Any], *path: str) -> Any:
    current: Any = row
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _ticker(row: dict[str, Any]) -> str:
    for value in (
        row.get("ticker"),
        _nested(row, "asset", "ticker"),
        _nested(row, "ranking", "ticker"),
    ):
        ticker = _clean_ticker(value)
        if ticker:
            return ticker
    return ""


def _status(row: dict[str, Any], *, short: bool = False) -> str:
    candidates = []
    if short:
        candidates.extend(
            [
                row.get("short_permission"),
                row.get("short_setup_status"),
            ]
        )
    candidates.extend(
        [
            row.get("status"),
            row.get("permission"),
            _nested(row, "permission", "status"),
            _nested(row, "validation", "status"),
            row.get("decision_label"),
            row.get("class"),
        ]
    )
    for value in candidates:
        if isinstance(value, dict):
            value = value.get("status")
        text = _as_text(value).upper()
        if text:
            return text
    return "-"


def _score(row: dict[str, Any]) -> float:
    for value in (
        row.get("score"),
        row.get("obs_index"),
        row.get("setup_score"),
        row.get("context_score"),
        _nested(row, "ranking", "context_score"),
        _nested(row, "ranking", "raw_score"),
    ):
        if value not in (None, ""):
            return round(_as_float(value), 4)
    return 0.0


def _reason(row: dict[str, Any]) -> str:
    direct = row.get("reason") or row.get("main_reason") or row.get("guard")
    if direct:
        return _as_text(direct)
    blockers = row.get("blocker_reasons") or row.get("blockers")
    if isinstance(blockers, list) and blockers:
        return ",".join(_as_text(item) for item in blockers if _as_text(item))
    for path in (("permission", "reasons"), ("validation", "reasons")):
        reasons = _nested(row, *path)
        if isinstance(reasons, list) and reasons:
            return ",".join(_as_text(item) for item in reasons if _as_text(item))
    return "-"


def _reference(row: dict[str, Any]) -> dict[str, Any]:
    ref_price = row.get("ref_price")
    if ref_price in (None, ""):
        ref_price = row.get("entry_price") or row.get("entry") or _nested(row, "asset", "last_close")
    return {
        "ref_price": round(_as_float(ref_price), 4) if _as_float(ref_price) > 0 else None,
        "ref_date": row.get("ref_date"),
        "ref_ts": row.get("ref_ts"),
        "ref_source": row.get("ref_source") or row.get("source"),
    }


def _is_short_ready(row: dict[str, Any]) -> bool:
    if _as_bool(row.get("executable")):
        return True
    return _status(row, short=True) in SHORT_READY_STATUSES


def _is_long_ready(row: dict[str, Any]) -> bool:
    return _status(row) in LONG_READY_STATUSES


def _row(
    row: dict[str, Any],
    *,
    table: str,
    side: str,
    source: str,
    rank: int,
) -> dict[str, Any]:
    reference = _reference(row)
    entry_price = _as_float(
        row.get("entry_price")
        or row.get("entry")
        or reference.get("ref_price")
        or _nested(row, "asset", "last_close")
    )
    return {
        "ticker": _ticker(row),
        "table": table,
        "bias": side,
        "side": side,
        "rank": int(row.get("rank") or rank),
        "score": _score(row),
        "status": _status(row, short=side == "SHORT"),
        "class": _as_text(row.get("class") or row.get("decision_label") or _status(row)),
        "reason": _reason(row),
        "entry_price": round(entry_price, 4) if entry_price > 0 else None,
        "ref_price": reference["ref_price"],
        "ref_date": reference["ref_date"],
        "ref_ts": reference["ref_ts"],
        "ref_source": reference["ref_source"],
        "source": source,
        "executable": _as_bool(row.get("executable")) or table.startswith("real_"),
        "raw": dict(row),
    }


def _append_unique(rows: list[dict[str, Any]], row: dict[str, Any]) -> None:
    ticker = row.get("ticker")
    if not ticker:
        return
    if any(existing.get("ticker") == ticker for existing in rows):
        return
    rows.append(row)


def _ensure_tables(tables: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    return {key: list(tables.get(key, [])) for key in TABLE_KEYS}


def _sort_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (-_as_float(row.get("score")), int(row.get("rank") or 9999)),
    )


def limit_tables(
    tables: dict[str, list[dict[str, Any]]],
    *,
    limit: int = DEFAULT_TABLE_LIMIT,
) -> dict[str, list[dict[str, Any]]]:
    """Return display rows without changing the complete snapshot tables."""
    resolved_limit = max(0, int(limit or 0))
    out: dict[str, list[dict[str, Any]]] = {}
    for key in TABLE_KEYS:
        rows = _sort_table([row for row in tables.get(key, []) if isinstance(row, dict)])
        out[key] = rows[:resolved_limit] if resolved_limit else rows
    return _ensure_tables(out)


def _capital_per_slot(capital: Any, slots: Any) -> float:
    slot_count = max(1, int(slots or 1))
    return round(_as_float(capital) / slot_count, 4)


def _market_regime_from_raw(raw_payload: dict[str, Any]) -> str:
    report = raw_payload.get("report") if isinstance(raw_payload.get("report"), dict) else {}
    for value in (
        _nested(raw_payload, "market", "regime"),
        _nested(report, "market_regime", "regime"),
        _nested(report, "market", "regime"),
    ):
        text = _as_text(value)
        if text:
            return text
    return "-"


def _model_from_raw(raw_payload: dict[str, Any]) -> str:
    report = raw_payload.get("report") if isinstance(raw_payload.get("report"), dict) else {}
    prediction = raw_payload.get("prediction") if isinstance(raw_payload.get("prediction"), dict) else {}
    report_prediction = report.get("prediction") if isinstance(report.get("prediction"), dict) else {}
    for payload in (prediction, report_prediction):
        for key in ("engine_used", "engine", "model", "meta_model"):
            text = _as_text(payload.get(key))
            if text:
                return text
    return "-"


def _with_missing_entry_reason(row: dict[str, Any], reason: str) -> dict[str, Any]:
    item = dict(row)
    item.setdefault("original_status", item.get("status", "-"))
    item["status"] = "NOT_REVIEWABLE"
    item["review_status"] = "NOT_REVIEWABLE"
    current_reason = _as_text(item.get("reason"), "-")
    item["reason"] = reason if current_reason in {"", "-"} else f"{current_reason}; {reason}"
    return item


def _display_limit(value: Any, default: int = DEFAULT_TABLE_LIMIT) -> int:
    if value in (None, ""):
        return max(0, int(default))
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return max(0, int(default))


def _full_snapshot_file(payload: dict[str, Any]) -> str:
    files = payload.get("files", {}) if isinstance(payload.get("files"), dict) else {}
    return _as_text(
        files.get("snapshot_json") or files.get("signal_source_file"),
        "-",
    )


def _clip(value: Any, width: int) -> str:
    text = _as_text(value, "-")
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "~"


def _fmt_score(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except Exception:
        return "-"


def _fmt_qty(value: Any) -> str:
    try:
        number = float(value)
    except Exception:
        return "-"
    if abs(number) >= 1000:
        return f"{number:,.0f}"
    if abs(number) >= 10:
        return f"{number:,.2f}"
    return f"{number:,.4f}"


def _review_verdict(*, trades: int, pnl: float) -> str:
    if trades <= 0:
        return "NO_REAL_TRADES"
    if pnl > 0:
        return "PROFIT"
    if pnl < 0:
        return "LOSS"
    return "FLAT"


def _row_outcome(amount: Any) -> str:
    if amount is None:
        return "NOT_REVIEWABLE"
    pnl = _as_float(amount)
    if pnl > 0:
        return "GAIN"
    if pnl < 0:
        return "LOSS"
    return "FLAT"


def update_data(
    *,
    list_name: str = "IBOV",
    start: str = "2000-01-01",
    end: str | None = None,
    tickers_file: str | None = None,
    prices_dir: str = "data/prices",
    indices_catalog: str = "config/indices_catalog.json",
    indices_dir: str = "data/indices",
    context_output: str = "storage/context/latest_market_context.json",
    universe_output: str = "data/universes/ibov_live.csv",
    features_config: str = "config/features.json",
    matrix_output: str = "storage/features/latest_feature_matrix.csv",
    context_config: str = "config/market_context.json",
    context_thresholds: str = "config/market_context_thresholds.json",
    use_cache: bool = True,
) -> dict[str, Any]:
    from aurum.cli_update import run_update_flow

    return run_update_flow(
        list_name=list_name,
        start=start,
        end=end,
        tickers_file=tickers_file,
        prices_dir=prices_dir,
        indices_catalog=indices_catalog,
        indices_dir=indices_dir,
        context_output=context_output,
        universe_output=universe_output,
        features_config=features_config,
        matrix_output=matrix_output,
        context_config=context_config,
        context_thresholds=context_thresholds,
        use_cache=use_cache,
    )


def build_features(update_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = update_payload or {}
    files = payload.get("files", {}) if isinstance(payload.get("files"), dict) else {}
    matrix = files.get("matrix") or "storage/features/latest_feature_matrix.csv"
    matrix_path = Path(str(matrix))
    return {
        "status": "OK" if matrix_path.exists() else "MISSING",
        "matrix": str(matrix),
        "rows": _count_csv_rows(matrix_path),
        "source": "update_data",
    }


def _count_csv_rows(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            return sum(1 for _ in csv.DictReader(file))
    except Exception:
        return 0


def generate_raw_signals(
    *,
    profile: str = "CON",
    list_name: str = "IBOV",
    policy: str = "config/policy.json",
    universe: str = "data/universes/ibov_live.csv",
    context: str = "storage/context/latest_market_context.json",
    matrix: str = "storage/features/latest_feature_matrix.csv",
    evaluation: str = "storage/prediction/latest_evaluation.json",
    prices_dir: str = "data/prices",
    observation_config: str = "config/observation.json",
    positions: str = "storage/positions/current_positions.csv",
    borrow_data: str = "data/borrow/borrow_rates.csv",
    limit: int = 20,
    run_dir: str = "storage/runs/latest",
    report_output: str = "storage/reports/latest_daily_report.txt",
    json_output: str = "storage/reports/latest_daily_report.json",
    basket: bool = False,
    slots: int = 5,
    min_sectors: int = 3,
    min_weight: float = 0.10,
    capital: float = 100000.0,
    risk_per_trade: float = 0.005,
    targets: int = 2,
    stop: str = "progressive",
    basket_output: str = "storage/baskets/latest_daily_basket.csv",
    allow_experimental_model: bool = False,
    db_path: str = "data/aurum.db",
    persist_db: bool = False,
) -> dict[str, Any]:
    from aurum.cli_run import run_decision_flow

    return run_decision_flow(
        profile=profile,
        list_name=list_name,
        policy=policy,
        universe=universe,
        context=context,
        matrix=matrix,
        evaluation=evaluation,
        prices_dir=prices_dir,
        observation_config=observation_config,
        positions=positions,
        borrow_data=borrow_data,
        limit=limit,
        run_dir=run_dir,
        report_output=report_output,
        json_output=json_output,
        basket=basket,
        slots=slots,
        min_sectors=min_sectors,
        min_weight=min_weight,
        capital=capital,
        risk_per_trade=risk_per_trade,
        targets=targets,
        stop=stop,
        basket_output=basket_output,
        allow_experimental_model=allow_experimental_model,
        db_path=db_path,
        persist_db=persist_db,
    )


def classify_into_four_tables(raw_payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    existing = payload.get("tables")
    if isinstance(existing, dict):
        out: dict[str, list[dict[str, Any]]] = {}
        for key in TABLE_KEYS:
            side = "SHORT" if key.endswith("short") else "LONG"
            out[key] = [
                _row(row, table=key, side=side, source="snapshot_table", rank=index)
                for index, row in enumerate(existing.get(key, []) or [], start=1)
                if isinstance(row, dict)
            ]
        return _ensure_tables(out)

    report = payload.get("report") if isinstance(payload.get("report"), dict) else {}
    decisions = report.get("decisions") or payload.get("decisions") or []
    observations = payload.get("observation_candidates") or report.get("observation_candidates") or []
    short_candidates = payload.get("short_candidates") or report.get("short_candidates") or []
    short_observations = (
        payload.get("short_observation_candidates")
        or report.get("short_observation_candidates")
        or []
    )

    tables: dict[str, list[dict[str, Any]]] = {key: [] for key in TABLE_KEYS}

    for index, item in enumerate(decisions if isinstance(decisions, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        if _is_long_ready(item):
            _append_unique(
                tables["real_long"],
                _row(item, table="real_long", side="LONG", source="decisions", rank=index),
            )
        else:
            _append_unique(
                tables["obs_long"],
                _row(item, table="obs_long", side="LONG", source="decisions", rank=index),
            )

    for index, item in enumerate(observations if isinstance(observations, list) else [], start=1):
        if isinstance(item, dict):
            _append_unique(
                tables["obs_long"],
                _row(item, table="obs_long", side="LONG", source="observation_candidates", rank=index),
            )

    for index, item in enumerate(short_candidates if isinstance(short_candidates, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        if _is_short_ready(item):
            _append_unique(
                tables["real_short"],
                _row(item, table="real_short", side="SHORT", source="short_candidates", rank=index),
            )
        else:
            _append_unique(
                tables["obs_short"],
                _row(item, table="obs_short", side="SHORT", source="short_candidates", rank=index),
            )

    for index, item in enumerate(short_observations if isinstance(short_observations, list) else [], start=1):
        if isinstance(item, dict):
            _append_unique(
                tables["obs_short"],
                _row(
                    item,
                    table="obs_short",
                    side="SHORT",
                    source="short_observation_candidates",
                    rank=index,
                ),
            )

    for key in TABLE_KEYS:
        tables[key] = _sort_table(tables[key])
    return _ensure_tables(tables)


def size_positions(
    tables: dict[str, list[dict[str, Any]]],
    *,
    capital: float = 100000.0,
    slots: int = 5,
    sizing_mode: str = "per_slot",
) -> dict[str, list[dict[str, Any]]]:
    slot_count = max(1, int(slots or 1))
    notional = round(float(capital or 0.0) / slot_count, 4)
    sized: dict[str, list[dict[str, Any]]] = {}
    for key in TABLE_KEYS:
        sized[key] = []
        for row in tables.get(key, []):
            item = dict(row)
            entry = _as_float(item.get("entry_price") or item.get("ref_price"))
            item["capital"] = float(capital or 0.0)
            item["slots"] = slot_count
            item["sizing_mode"] = sizing_mode
            item["notional"] = notional
            item["position_size"] = notional
            item["quantity"] = round(notional / entry, 6) if entry > 0 else None
            sized[key].append(item)
    return _ensure_tables(sized)


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value.upper()).strip("_") or "AURUM"


def signal_snapshot_paths(
    *,
    profile: str = "CON",
    list_name: str = "IBOV",
    signal_date: str | None = None,
    signals_dir: str | Path = "storage/signals",
) -> dict[str, Path]:
    day = signal_date or _today()
    stem = f"{_slug(profile)}_{_slug(list_name)}_signal"
    root = Path(signals_dir) / day
    return {
        "root": root,
        "json": root / f"{stem}.json",
        "txt": root / f"{stem}.txt",
    }


def save_signal_snapshot(
    snapshot: dict[str, Any],
    *,
    signals_dir: str | Path = "storage/signals",
    force: bool = False,
) -> dict[str, str]:
    paths = signal_snapshot_paths(
        profile=_as_text(snapshot.get("profile"), "CON"),
        list_name=_as_text(snapshot.get("list"), "IBOV"),
        signal_date=_as_text(snapshot.get("signal_date"), _today()),
        signals_dir=signals_dir,
    )
    paths["root"].mkdir(parents=True, exist_ok=True)
    if not force and (paths["json"].exists() or paths["txt"].exists()):
        raise FileExistsError(f"signal snapshot already exists: {paths['json']}")

    payload = dict(snapshot)
    payload.setdefault("files", {})
    payload["files"] = {
        **payload["files"],
        "snapshot_json": str(paths["json"]),
        "snapshot_txt": str(paths["txt"]),
    }
    paths["json"].write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["txt"].write_text(render_daily_report(payload), encoding="utf-8")
    return {
        "snapshot_json": str(paths["json"]),
        "snapshot_txt": str(paths["txt"]),
    }


def load_signal_snapshot(
    *,
    profile: str = "CON",
    list_name: str = "IBOV",
    signal_date: str | None = None,
    review_date: str | None = None,
    signals_dir: str | Path = "storage/signals",
) -> dict[str, Any]:
    if signal_date:
        path = signal_snapshot_paths(
            profile=profile,
            list_name=list_name,
            signal_date=signal_date,
            signals_dir=signals_dir,
        )["json"]
        if not path.exists():
            raise FileNotFoundError(f"signal snapshot not found: {path}")
        return _load_snapshot_file(path)

    root = Path(signals_dir)
    cutoff = review_date or _today()
    candidates: list[Path] = []
    if root.exists():
        for day_dir in root.iterdir():
            if not day_dir.is_dir():
                continue
            day = day_dir.name
            if day >= cutoff:
                continue
            path = signal_snapshot_paths(
                profile=profile,
                list_name=list_name,
                signal_date=day,
                signals_dir=signals_dir,
            )["json"]
            if path.exists():
                candidates.append(path)
    if not candidates:
        raise FileNotFoundError(
            f"no previous signal snapshot for {profile}/{list_name} before {cutoff}"
        )
    return _load_snapshot_file(sorted(candidates)[-1])


def _load_snapshot_file(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"signal snapshot must be a JSON object: {path}")
    payload.setdefault("files", {})
    payload["files"]["signal_source_file"] = str(path)
    return payload


def _price_file(prices_dir: str | Path, ticker: str) -> Path:
    base = Path(prices_dir)
    clean = _clean_ticker(ticker)
    candidates = [
        base / f"{clean}.SA.csv",
        base / f"{clean}.csv",
        base / f"{clean.lower()}.SA.csv",
        base / f"{clean.lower()}.csv",
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def _latest_price(
    ticker: str,
    *,
    prices_dir: str | Path = "data/prices",
    max_date: str | None = None,
) -> dict[str, Any]:
    path = _price_file(prices_dir, ticker)
    if not path.exists():
        return {"status": "DATA_MISSING", "price": None, "date": None, "source": str(path)}
    latest_date = ""
    latest_close = 0.0
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                row_date = _as_text(row.get("date"))
                close = _as_float(row.get("close"))
                if not row_date or close <= 0:
                    continue
                if max_date and row_date > max_date:
                    continue
                if row_date >= latest_date:
                    latest_date = row_date
                    latest_close = close
    except Exception as exc:
        return {
            "status": "DATA_ERROR",
            "price": None,
            "date": None,
            "source": str(path),
            "error": str(exc),
        }
    if not latest_date or latest_close <= 0:
        return {"status": "DATA_MISSING", "price": None, "date": None, "source": str(path)}
    return {
        "status": "OK",
        "price": round(latest_close, 4),
        "date": latest_date,
        "source": str(path),
    }


def _hydrate_entries_for_review(
    tables: dict[str, list[dict[str, Any]]],
    *,
    prices_dir: str | Path,
    signal_date: str | None,
) -> dict[str, list[dict[str, Any]]]:
    hydrated: dict[str, list[dict[str, Any]]] = {}
    for key in TABLE_KEYS:
        hydrated[key] = []
        for row in tables.get(key, []) or []:
            if not isinstance(row, dict):
                continue
            item = dict(row)
            entry = _as_float(item.get("entry_price") or item.get("ref_price"))
            if entry > 0:
                item["entry_price"] = round(entry, 4)
                item.setdefault("entry_status", "OK")
                hydrated[key].append(item)
                continue

            latest = _latest_price(
                item.get("ticker", ""),
                prices_dir=prices_dir,
                max_date=signal_date,
            )
            latest_price = _as_float(latest.get("price"))
            if latest_price > 0:
                item["entry_price"] = round(latest_price, 4)
                item["ref_price"] = item.get("ref_price") or round(latest_price, 4)
                item["ref_date"] = item.get("ref_date") or latest.get("date")
                item["ref_source"] = item.get("ref_source") or latest.get("source")
                item["entry_status"] = "OK_FROM_LOCAL_PRICE"
            else:
                item = _with_missing_entry_reason(
                    item,
                    "missing entry price; no local price available",
                )
                item["entry_status"] = latest.get("status") or "DATA_MISSING"
            hydrated[key].append(item)
    return _ensure_tables(hydrated)


def _review_row(
    row: dict[str, Any],
    *,
    table: str,
    prices_dir: str | Path,
    review_date: str,
) -> dict[str, Any]:
    latest = _latest_price(row.get("ticker", ""), prices_dir=prices_dir, max_date=review_date)
    entry = _as_float(row.get("entry_price") or row.get("ref_price"))
    notional = _as_float(row.get("notional") or row.get("position_size"))
    latest_price = _as_float(latest.get("price"))
    is_short = table.endswith("short")
    is_real = table.startswith("real_")
    reasons: list[str] = []
    if entry <= 0:
        reasons.append("missing entry price")
    if notional <= 0:
        reasons.append("missing capital/notional")
    if latest.get("status") != "OK" or latest_price <= 0:
        reasons.append(f"latest price unavailable ({latest.get('status') or 'DATA_MISSING'})")

    ret = None
    amount = None
    reviewable = not reasons
    if reviewable:
        ret = (entry - latest_price) / entry if is_short else (latest_price - entry) / entry
        amount = round(notional * ret, 4)
    current_reason = _as_text(row.get("reason"), "-")
    if reasons:
        detail = "; ".join(reasons)
        reason = detail if current_reason in {"", "-"} else f"{current_reason}; {detail}"
    else:
        reason = current_reason
    review_status = _row_outcome(amount) if reviewable else "NOT_REVIEWABLE"
    result = dict(row)
    result.update(
        {
            "review_date": review_date,
            "entry_price": round(entry, 4) if entry > 0 else row.get("entry_price"),
            "latest_price": latest.get("price"),
            "latest_date": latest.get("date"),
            "latest_source": latest.get("source"),
            "data_status": latest.get("status"),
            "review_status": review_status,
            "reviewable": reviewable,
            "return_pct": round(ret * 100, 4) if ret is not None else None,
            "pnl": amount if is_real else None,
            "would_pnl": amount if not is_real else None,
            "reason": reason,
        }
    )
    if not reviewable:
        result.setdefault("original_status", result.get("status", "-"))
        result["status"] = "NOT_REVIEWABLE"
    return result


def review_four_tables(
    snapshot: dict[str, Any],
    *,
    review_date: str | None = None,
    prices_dir: str | Path = "data/prices",
    review_limit: int = DEFAULT_REVIEW_LIMIT,
) -> dict[str, Any]:
    resolved_review_date = review_date or _today()
    resolved_review_limit = _display_limit(review_limit, DEFAULT_REVIEW_LIMIT)
    source_files = snapshot.get("files", {}) if isinstance(snapshot.get("files"), dict) else {}
    reviewed_tables: dict[str, list[dict[str, Any]]] = {}
    summary: dict[str, dict[str, Any]] = {}

    tables = snapshot.get("tables", {}) if isinstance(snapshot.get("tables"), dict) else {}
    for key in TABLE_KEYS:
        rows = [
            _review_row(row, table=key, prices_dir=prices_dir, review_date=resolved_review_date)
            for row in tables.get(key, []) or []
            if isinstance(row, dict)
        ]
        reviewed_tables[key] = rows
        real_total = round(sum(_as_float(row.get("pnl")) for row in rows), 4)
        obs_total = round(sum(_as_float(row.get("would_pnl")) for row in rows), 4)
        returns = [row.get("return_pct") for row in rows if row.get("return_pct") is not None]
        reviewable_items = sum(1 for row in rows if row.get("reviewable"))
        summary[key] = {
            "title": TABLE_TITLES[key],
            "items": len(rows),
            "shown_items": min(len(rows), resolved_review_limit) if resolved_review_limit else len(rows),
            "total_items": len(rows),
            "review_scope": "FULL_SNAPSHOT",
            "reviewable_items": reviewable_items,
            "not_reviewable_items": len(rows) - reviewable_items,
            "data_missing": sum(1 for row in rows if row.get("data_status") != "OK"),
            "notional_per_item": rows[0].get("notional") if rows else 0.0,
            "real_pnl": real_total if key.startswith("real_") else 0.0,
            "would_pnl": obs_total if key.startswith("obs_") else 0.0,
            "pnl_total": real_total if key.startswith("real_") else obs_total,
            "avg_return_pct": round(sum(_as_float(value) for value in returns) / len(returns), 4)
            if returns
            else None,
        }

    real_long_pnl = round(_as_float(summary.get("real_long", {}).get("real_pnl")), 4)
    real_short_pnl = round(_as_float(summary.get("real_short", {}).get("real_pnl")), 4)
    real_total_pnl = round(real_long_pnl + real_short_pnl, 4)
    real_trades = int(summary.get("real_long", {}).get("items", 0)) + int(
        summary.get("real_short", {}).get("items", 0)
    )
    real_reviewable_trades = int(summary.get("real_long", {}).get("reviewable_items", 0)) + int(
        summary.get("real_short", {}).get("reviewable_items", 0)
    )
    if real_trades > 0 and real_reviewable_trades == 0:
        real_verdict = "REAL_NOT_REVIEWABLE"
    else:
        real_verdict = _review_verdict(trades=real_trades, pnl=real_total_pnl)

    obs_long_pnl = round(_as_float(summary.get("obs_long", {}).get("would_pnl")), 4)
    obs_short_pnl = round(_as_float(summary.get("obs_short", {}).get("would_pnl")), 4)
    obs_total_pnl = round(obs_long_pnl + obs_short_pnl, 4)
    obs_items = int(summary.get("obs_long", {}).get("items", 0)) + int(
        summary.get("obs_short", {}).get("items", 0)
    )
    obs_reviewable_items = int(summary.get("obs_long", {}).get("reviewable_items", 0)) + int(
        summary.get("obs_short", {}).get("reviewable_items", 0)
    )
    price_dates = [
        _as_text(row.get("latest_date"))
        for rows in reviewed_tables.values()
        for row in rows
        if _as_text(row.get("latest_date"))
    ]
    operational_result = {
        "real_long_pnl": real_long_pnl,
        "real_short_pnl": real_short_pnl,
        "real_total_pnl": real_total_pnl,
        "real_trades": real_trades,
        "real_reviewable_trades": real_reviewable_trades,
        "real_verdict": real_verdict,
    }
    observation_result = {
        "obs_long_pnl": obs_long_pnl,
        "obs_short_pnl": obs_short_pnl,
        "obs_total_pnl": obs_total_pnl,
        "obs_items": obs_items,
        "obs_reviewable_items": obs_reviewable_items,
        "obs_not_reviewable_items": obs_items - obs_reviewable_items,
        "obs_verdict": "STUDY_ONLY",
    }
    final = {
        "operational_pnl": real_total_pnl if real_trades else 0.0,
        "paper_pnl": obs_total_pnl,
        "final_verdict": real_verdict,
    }

    payload = {
        "schema_version": "aurum_review.v1",
        "created_at": _now_ts(),
        "profile": snapshot.get("profile", "CON"),
        "list": snapshot.get("list", "IBOV"),
        "signal_date": snapshot.get("signal_date"),
        "review_date": resolved_review_date,
        "prices_dir": str(prices_dir),
        "signal_source_file": source_files.get("signal_source_file")
        or source_files.get("snapshot_json"),
        "full_snapshot_file": source_files.get("signal_source_file")
        or source_files.get("snapshot_json"),
        "prices_last_date": max(price_dates) if price_dates else "-",
        "capital": snapshot.get("capital"),
        "slots": snapshot.get("slots"),
        "capital_per_slot": snapshot.get("capital_per_slot")
        or _capital_per_slot(snapshot.get("capital"), snapshot.get("slots")),
        "sizing_mode": snapshot.get("sizing_mode", "per_slot"),
        "review_limit": resolved_review_limit,
        "review_scope": "FULL_SNAPSHOT",
        "tables": reviewed_tables,
        "summary": summary,
        "operational_result": operational_result,
        "observation_result": observation_result,
        "final": final,
    }
    payload["text"] = render_review_report(payload)
    return payload


def _fmt_money(value: Any) -> str:
    try:
        return f"{float(value):,.2f}"
    except Exception:
        return "-"


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value):+.2f}%"
    except Exception:
        return "-"


def _daily_table_header() -> str:
    return (
        f"{'#':>2}  {'TICKER':<10} {'SCORE':>7} {'ENTRY':>12} "
        f"{'CAPITAL':>12} {'QTY':>12} {'STATUS':<16} {'REASON':<48}"
    )


def _review_table_header() -> str:
    return (
        f"{'#':>2}  {'TICKER':<10} {'ENTRY':>12} {'LATEST':>12} "
        f"{'RET':>9} {'PNL':>12} {'STATUS':<16} {'REASON':<48}"
    )


def _render_signal_table(
    lines: list[str],
    title: str,
    rows: list[dict[str, Any]],
    *,
    total_count: int,
    limit: int,
    full_snapshot_file: str,
) -> None:
    shown_count = len(rows)
    lines.extend([f"{title} | TOP {shown_count} OF {total_count}", "-" * 120])
    lines.append(
        f"shown_items={shown_count} total_items={total_count} "
        f"review_scope=FULL_SNAPSHOT full_snapshot_file={full_snapshot_file}"
    )
    lines.append("Full list saved in snapshot.")
    if not rows:
        lines.extend(["NO ITEMS", ""])
        return
    header = _daily_table_header()
    lines.extend([header, "-" * len(header)])
    for index, row in enumerate(rows, start=1):
        lines.append(
            f"{index:>2}  "
            f"{_clip(row.get('ticker'), 10):<10} "
            f"{_fmt_score(row.get('score')):>7} "
            f"{_fmt_money(row.get('entry_price')):>12} "
            f"{_fmt_money(row.get('notional')):>12} "
            f"{_fmt_qty(row.get('quantity')):>12} "
            f"{_clip(row.get('status'), 16):<16} "
            f"{_clip(row.get('reason'), 48):<48}"
        )
    lines.append("")


def render_daily_report(snapshot: dict[str, Any]) -> str:
    tables = snapshot.get("tables", {}) if isinstance(snapshot.get("tables"), dict) else {}
    counts = {key: len(tables.get(key, []) or []) for key in TABLE_KEYS}
    raw_counts = snapshot.get("raw_counts", {}) if isinstance(snapshot.get("raw_counts"), dict) else counts
    limit = _display_limit(snapshot.get("display_limit", snapshot.get("table_limit")), DEFAULT_TABLE_LIMIT)
    display_tables = limit_tables(tables, limit=limit)
    shown_counts = {key: len(display_tables.get(key, []) or []) for key in TABLE_KEYS}
    snapshot_json = _full_snapshot_file(snapshot)
    capital_per_slot = snapshot.get("capital_per_slot") or _capital_per_slot(
        snapshot.get("capital"),
        snapshot.get("slots"),
    )
    lines = [
        "AURUM DAILY SIGNALS",
        "-" * 120,
        f"date={snapshot.get('signal_date', '-')}",
        f"profile={snapshot.get('profile', '-')}",
        f"list={snapshot.get('list', '-')}",
        f"capital={_fmt_money(snapshot.get('capital'))}",
        f"slots={snapshot.get('slots', '-')}",
        f"capital_per_slot={_fmt_money(capital_per_slot)}",
        f"market_regime={snapshot.get('market_regime', '-')}",
        f"model={snapshot.get('model', '-')}",
        f"snapshot_json={snapshot_json}",
        f"display_limit={limit}",
        "review_scope=FULL_SNAPSHOT",
        "",
        "BOARD",
        "-" * 120,
    ]
    for key in TABLE_KEYS:
        total = int(raw_counts.get(key, counts[key]) or counts[key])
        lines.append(
            f"{TABLE_TITLES[key]}: shown_items={shown_counts[key]} "
            f"total_items={total} review_scope=FULL_SNAPSHOT "
            f"full_snapshot_file={snapshot_json}"
        )
    lines.append("")
    for key in TABLE_KEYS:
        _render_signal_table(
            lines,
            TABLE_TITLES[key],
            display_tables.get(key, []),
            total_count=int(raw_counts.get(key, counts[key]) or counts[key]),
            limit=limit,
            full_snapshot_file=snapshot_json,
        )
    lines.extend(
        [
            "SUMMARY",
            "-" * 120,
        ]
    )
    for key in TABLE_KEYS:
        total = int(raw_counts.get(key, counts[key]) or counts[key])
        lines.append(
            f"{TABLE_TITLES[key]} shown_items={shown_counts[key]} "
            f"total_items={total} review_scope=FULL_SNAPSHOT"
        )
    lines.extend(
        [
            "",
            "FILES",
            "-" * 120,
        ]
    )
    files = snapshot.get("files", {}) if isinstance(snapshot.get("files"), dict) else {}
    for key in sorted(files):
        lines.append(f"{key}={files[key]}")
    return "\n".join(lines).rstrip() + "\n"


def _render_review_table(
    lines: list[str],
    title: str,
    rows: list[dict[str, Any]],
    *,
    total_count: int,
    review_limit: int,
    full_snapshot_file: str,
) -> None:
    display_rows = rows[:review_limit] if review_limit else rows
    shown_count = len(display_rows)
    lines.extend([f"{title} | TOP {shown_count} OF {total_count}", "-" * 120])
    lines.append(
        f"shown_items={shown_count} total_items={total_count} "
        f"review_scope=FULL_SNAPSHOT full_snapshot_file={full_snapshot_file}"
    )
    if not rows:
        lines.extend(["NO ITEMS", ""])
        return
    header = _review_table_header()
    lines.extend([header, "-" * len(header)])
    for index, row in enumerate(display_rows, start=1):
        amount = row.get("pnl") if row.get("pnl") is not None else row.get("would_pnl")
        lines.append(
            f"{index:>2}  "
            f"{_clip(row.get('ticker'), 10):<10} "
            f"{_fmt_money(row.get('entry_price')):>12} "
            f"{_fmt_money(row.get('latest_price')):>12} "
            f"{_fmt_pct(row.get('return_pct')):>9} "
            f"{_fmt_money(amount):>12} "
            f"{_clip(row.get('review_status'), 16):<16} "
            f"{_clip(row.get('reason'), 48):<48}"
        )
    lines.append("")


def render_review_report(review: dict[str, Any]) -> str:
    tables = review.get("tables", {}) if isinstance(review.get("tables"), dict) else {}
    summary = review.get("summary", {}) if isinstance(review.get("summary"), dict) else {}
    operational = review.get("operational_result", {}) if isinstance(review.get("operational_result"), dict) else {}
    observation = review.get("observation_result", {}) if isinstance(review.get("observation_result"), dict) else {}
    final = review.get("final", {}) if isinstance(review.get("final"), dict) else {}
    review_limit = _display_limit(review.get("review_limit"), DEFAULT_REVIEW_LIMIT)
    full_snapshot_file = _as_text(review.get("full_snapshot_file") or review.get("signal_source_file"), "-")
    lines = [
        "AURUM REVIEW",
        "-" * 120,
        f"signal_date={review.get('signal_date', '-')}",
        f"review_date={review.get('review_date', '-')}",
        f"signal_source_file={review.get('signal_source_file', '-')}",
        f"prices_last_date={review.get('prices_last_date', '-')}",
        f"capital={_fmt_money(review.get('capital'))}",
        f"slots={review.get('slots', '-')}",
        f"capital_per_slot={_fmt_money(review.get('capital_per_slot'))}",
        f"profile={review.get('profile', '-')} list={review.get('list', '-')}",
        f"review_limit={review_limit}",
        "review_scope=FULL_SNAPSHOT",
        "",
    ]
    for key in TABLE_KEYS:
        rows = tables.get(key, []) or []
        total = int(summary.get(key, {}).get("total_items") or len(rows))
        _render_review_table(
            lines,
            REVIEW_TITLES[key],
            rows,
            total_count=total,
            review_limit=review_limit,
            full_snapshot_file=full_snapshot_file,
        )
    lines.extend(
        [
            "OPERATIONAL RESULT",
            "-" * 120,
            f"real_long_pnl={_fmt_money(operational.get('real_long_pnl'))}",
            f"real_short_pnl={_fmt_money(operational.get('real_short_pnl'))}",
            f"real_total_pnl={_fmt_money(operational.get('real_total_pnl'))}",
            f"real_trades={operational.get('real_trades', 0)}",
            f"real_verdict={operational.get('real_verdict', '-')}",
            "",
            "OBSERVATION RESULT",
            "-" * 120,
            f"obs_long_pnl={_fmt_money(observation.get('obs_long_pnl'))}",
            f"obs_short_pnl={_fmt_money(observation.get('obs_short_pnl'))}",
            f"obs_total_pnl={_fmt_money(observation.get('obs_total_pnl'))}",
            f"obs_items={observation.get('obs_items', 0)}",
            f"obs_reviewable_items={observation.get('obs_reviewable_items', 0)}",
            f"obs_not_reviewable_items={observation.get('obs_not_reviewable_items', 0)}",
            f"obs_verdict={observation.get('obs_verdict', 'STUDY_ONLY')}",
            "",
            "FINAL",
            "-" * 120,
            f"operational_pnl={_fmt_money(final.get('operational_pnl'))}",
            f"paper_pnl={_fmt_money(final.get('paper_pnl'))}",
            f"final_verdict={final.get('final_verdict', '-')}",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def run_daily(
    *,
    profile: str = "CON",
    list_name: str = "IBOV",
    capital: float = 100000.0,
    slots: int = 5,
    signal_date: str | None = None,
    signals_dir: str | Path = "storage/signals",
    prices_dir: str = "data/prices",
    update: bool = True,
    force: bool = False,
    display_limit: int = DEFAULT_TABLE_LIMIT,
    table_limit: int | None = None,
    raw_payload: dict[str, Any] | None = None,
    update_payload: dict[str, Any] | None = None,
    **signal_kwargs: Any,
) -> dict[str, Any]:
    resolved_signal_date = signal_date or _today()
    resolved_display_limit = _display_limit(
        table_limit if table_limit is not None else display_limit,
        DEFAULT_TABLE_LIMIT,
    )
    resolved_update = update_payload
    features: dict[str, Any] = {}
    if update and resolved_update is None:
        resolved_update = update_data(list_name=list_name, prices_dir=prices_dir)
    if resolved_update is not None:
        features = build_features(resolved_update)

    raw = raw_payload or generate_raw_signals(
        profile=profile,
        list_name=list_name,
        capital=capital,
        slots=slots,
        prices_dir=prices_dir,
        **signal_kwargs,
    )
    raw_tables = classify_into_four_tables(raw)
    raw_counts = {key: len(raw_tables.get(key, [])) for key in TABLE_KEYS}
    review_ready_tables = _hydrate_entries_for_review(
        raw_tables,
        prices_dir=prices_dir,
        signal_date=resolved_signal_date,
    )
    tables = size_positions(
        review_ready_tables,
        capital=capital,
        slots=slots,
        sizing_mode="per_slot",
    )
    counts = {key: len(tables.get(key, [])) for key in TABLE_KEYS}
    snapshot = {
        "schema_version": "aurum_signal_snapshot.v1",
        "created_at": _now_ts(),
        "signal_date": resolved_signal_date,
        "profile": profile.upper(),
        "list": list_name.upper(),
        "capital": float(capital),
        "slots": max(1, int(slots or 1)),
        "capital_per_slot": _capital_per_slot(capital, slots),
        "sizing_mode": "per_slot",
        "display_limit": resolved_display_limit,
        "table_limit": resolved_display_limit,
        "review_scope": "FULL_SNAPSHOT",
        "market_regime": _market_regime_from_raw(raw) if isinstance(raw, dict) else "-",
        "model": _model_from_raw(raw) if isinstance(raw, dict) else "-",
        "raw_status": raw.get("status") if isinstance(raw, dict) else "-",
        "update": resolved_update or {},
        "features": features,
        "tables": tables,
        "counts": counts,
        "raw_counts": raw_counts,
        "shown_counts": {
            key: min(counts[key], resolved_display_limit) if resolved_display_limit else counts[key]
            for key in TABLE_KEYS
        },
        "files": {},
    }
    files = save_signal_snapshot(snapshot, signals_dir=signals_dir, force=force)
    snapshot["files"] = dict(files)
    snapshot["text"] = render_daily_report(snapshot)
    return snapshot


def run_review(
    *,
    profile: str = "CON",
    list_name: str = "IBOV",
    signal_date: str | None = None,
    review_date: str | None = None,
    signals_dir: str | Path = "storage/signals",
    prices_dir: str | Path = "data/prices",
    review_limit: int = DEFAULT_REVIEW_LIMIT,
) -> dict[str, Any]:
    snapshot = load_signal_snapshot(
        profile=profile,
        list_name=list_name,
        signal_date=signal_date,
        review_date=review_date,
        signals_dir=signals_dir,
    )
    return review_four_tables(
        snapshot,
        review_date=review_date,
        prices_dir=prices_dir,
        review_limit=review_limit,
    )


def train_models(**kwargs: Any) -> dict[str, Any]:
    from aurum.cli_train import run_train_flow

    return run_train_flow(**kwargs)


def evaluate_features(*, record: bool = False) -> dict[str, Any]:
    from aurum.training.audit import build_train_audit

    return build_train_audit(record=record)


def evaluate_engines() -> dict[str, Any]:
    from aurum.engines.scoreboard import build_scoreboard

    return build_scoreboard()


def render_weekly_report(payload: dict[str, Any]) -> str:
    lines = [
        "AURUM WEEKLY TRAINING",
        "-" * 80,
        f"created_at={payload.get('created_at', '-')}",
        "",
        "UPDATE",
        "-" * 80,
        f"status={payload.get('update', {}).get('status', '-')}",
        "",
        "FEATURES",
        "-" * 80,
        f"status={payload.get('features', {}).get('status', '-')} "
        f"rows={payload.get('features', {}).get('rows', '-')}",
        "",
        "TRAINING",
        "-" * 80,
        f"status={payload.get('training', {}).get('status', '-')}",
        f"reason={payload.get('training', {}).get('reason', '-')}",
        "",
        "FEATURE AUDIT",
        "-" * 80,
        f"status={payload.get('feature_audit', {}).get('status', '-')}",
        f"verdict={payload.get('feature_audit', {}).get('verdict', '-')}",
        "",
        "ENGINE AUDIT",
        "-" * 80,
        f"best_engine={payload.get('engine_audit', {}).get('best_engine', '-')}",
        f"most_reliable_horizon={payload.get('engine_audit', {}).get('most_reliable_horizon', '-')}",
        "",
        "FINAL",
        "-" * 80,
        f"status={payload.get('status', '-')}",
    ]
    return "\n".join(lines).rstrip() + "\n"


def run_weekly(
    *,
    list_name: str = "IBOV",
    output: str | Path = "storage/reports/latest_weekly_report.txt",
    update: bool = True,
    train: bool = True,
    **train_kwargs: Any,
) -> dict[str, Any]:
    update_payload: dict[str, Any] = {}
    features: dict[str, Any] = {}
    if update:
        update_payload = update_data(list_name=list_name)
        features = build_features(update_payload)
    training = train_models(**train_kwargs) if train else {"status": "SKIPPED"}
    feature_audit = evaluate_features(record=False)
    engine_audit = evaluate_engines()
    payload = {
        "schema_version": "aurum_weekly.v1",
        "created_at": _now_ts(),
        "list": list_name.upper(),
        "status": training.get("status", "OK"),
        "update": update_payload,
        "features": features,
        "training": training,
        "feature_audit": feature_audit,
        "engine_audit": engine_audit,
    }
    payload["text"] = render_weekly_report(payload)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(payload["text"], encoding="utf-8")
    payload["files"] = {"weekly_report": str(output_path)}
    return payload
