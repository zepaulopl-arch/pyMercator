from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pymercator.storage.db import DEFAULT_DB_PATH, SCHEMA_VERSION, connect, init_db


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value)
    return text if text else default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _nested(payload: dict[str, Any], *keys: str, default: Any = "") -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def _report_paths(payload: dict[str, Any]) -> dict[str, str]:
    files = _as_dict(payload.get("files"))
    return {
        "report_json": _text(files.get("json")),
        "report_txt": _text(files.get("report")),
        "basket_csv": _text(files.get("basket")),
        "run_dir": _text(files.get("run_dir")),
    }


def _daily_run_row(payload: dict[str, Any], created_at: str) -> dict[str, Any]:
    market = _as_dict(payload.get("market"))
    context_summary = _as_dict(market.get("context_summary"))
    prediction = _as_dict(payload.get("prediction"))
    model_quality = _as_dict(prediction.get("model_quality"))
    decision = _as_dict(payload.get("decision"))
    basket = _as_dict(payload.get("basket"))
    paths = _report_paths(payload)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_date": created_at[:10],
        "created_at": created_at,
        "profile": _text(payload.get("profile"), "-"),
        "list_name": _text(payload.get("list"), "-"),
        "status": _text(payload.get("status"), "-"),
        "reason": _text(payload.get("reason")),
        "market": _text(market.get("regime")),
        "trend": _text(context_summary.get("market_trend")),
        "model_quality": _text(model_quality.get("status")),
        "behavior": _text(prediction.get("behavior")),
        "long_basket_status": _text(basket.get("status")),
        "actionable": _int(decision.get("actionable")),
        "watch": _int(decision.get("watch")),
        "blocked": _int(decision.get("blocked")),
        "report_json": paths["report_json"],
        "report_txt": paths["report_txt"],
        "basket_csv": paths["basket_csv"],
        "run_dir": paths["run_dir"],
        "payload_json": _json_text(payload),
    }


def _dedupe_reasons(items: Iterable[tuple[str, Any]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    rows: list[tuple[str, str]] = []
    for reason_type, value in items:
        if value is None:
            continue
        values = value if isinstance(value, list | tuple | set) else [value]
        for item in values:
            reason = _text(item)
            if not reason:
                continue
            key = (_text(reason_type, "reason"), reason)
            if key in seen:
                continue
            seen.add(key)
            rows.append(key)
    return rows


def _decision_signal(decision: dict[str, Any]) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    asset = _as_dict(decision.get("asset"))
    permission = _as_dict(decision.get("permission"))
    ranking = _as_dict(decision.get("ranking"))
    validation = _as_dict(decision.get("validation"))
    status = _text(permission.get("status") or validation.get("status"))
    signal = {
        "ticker": _text(asset.get("ticker"), "-").upper(),
        "bias": "LONG",
        "action": status,
        "status": status,
        "score": _float_or_none(ranking.get("context_score") or ranking.get("score")),
        "signal_class": _text(decision.get("decision_label") or status),
        "executable": 1 if status == "READY" else 0,
        "borrow_status": "",
        "permission": status,
        "source": "decision",
        "payload_json": _json_text(decision),
    }
    reasons = _dedupe_reasons(
        [
            ("blocker", decision.get("blocker_reasons")),
            ("code", decision.get("decision_codes")),
            ("permission", permission.get("reasons")),
            ("validation", validation.get("reasons")),
            ("reason", decision.get("reason")),
        ]
    )
    return signal, reasons


def _observation_signal(row: dict[str, Any], *, source: str, bias: str) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    signal_class = _text(row.get("class") or row.get("short_setup_status") or row.get("status"))
    permission = _text(row.get("permission") or row.get("short_permission"))
    status = _text(row.get("status") or permission or signal_class)
    signal = {
        "ticker": _text(row.get("ticker") or row.get("target"), "-").upper(),
        "bias": _text(row.get("bias"), bias).upper(),
        "action": _text(row.get("action") or permission or status),
        "status": status,
        "score": _float_or_none(row.get("score") or row.get("obs_index") or row.get("short_score")),
        "signal_class": signal_class,
        "executable": 1 if bool(row.get("executable")) else 0,
        "borrow_status": _text(row.get("borrow_status")),
        "permission": permission,
        "source": source,
        "payload_json": _json_text(row),
    }
    reasons = _dedupe_reasons(
        [
            ("reason", row.get("reason")),
            ("setup", row.get("setup_reason")),
            ("risk", row.get("risk_reason")),
            ("borrow", row.get("borrow_reason")),
            ("event", row.get("event_reason")),
        ]
    )
    return signal, reasons


def _hedge_signal(row: dict[str, Any]) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    ticker = row.get("ticker") or row.get("target") or row.get("TARGET")
    status = row.get("status") or row.get("action") or row.get("ACTION")
    signal = {
        "ticker": _text(ticker, "-").upper(),
        "bias": "HEDGE",
        "action": _text(row.get("action") or row.get("ACTION") or status),
        "status": _text(status),
        "score": _float_or_none(row.get("score")),
        "signal_class": _text(row.get("class") or row.get("status") or row.get("action")),
        "executable": 1 if bool(row.get("executable")) else 0,
        "borrow_status": "",
        "permission": _text(row.get("permission")),
        "source": "hedge",
        "payload_json": _json_text(row),
    }
    return signal, _dedupe_reasons([("reason", row.get("reason") or row.get("REASON"))])


def _signals_from_payload(payload: dict[str, Any]) -> list[tuple[dict[str, Any], list[tuple[str, str]]]]:
    rows: list[tuple[dict[str, Any], list[tuple[str, str]]]] = []
    report = _as_dict(payload.get("report"))
    for decision in _as_list(report.get("decisions")):
        if isinstance(decision, dict):
            rows.append(_decision_signal(decision))
    for item in _as_list(payload.get("observation_candidates")):
        if isinstance(item, dict):
            rows.append(_observation_signal(item, source="long_observation", bias="LONG"))
    for item in _as_list(payload.get("short_observation_candidates")):
        if isinstance(item, dict):
            rows.append(_observation_signal(item, source="short_observation", bias="SHORT"))
    for item in _as_list(payload.get("short_candidates")):
        if isinstance(item, dict):
            rows.append(_observation_signal(item, source="short_setup", bias="SHORT"))
    for item in _as_list(payload.get("hedge_candidates")):
        if isinstance(item, dict):
            rows.append(_hedge_signal(item))
    return rows


def _rankings_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rankings: list[dict[str, Any]] = []
    top_rows = _as_list(payload.get("top"))
    if not top_rows:
        top_rows = _as_list(_as_dict(payload.get("report")).get("decisions"))
    for index, row in enumerate(top_rows, start=1):
        if not isinstance(row, dict):
            continue
        asset = _as_dict(row.get("asset"))
        ranking = _as_dict(row.get("ranking"))
        permission = _as_dict(row.get("permission"))
        ticker = row.get("ticker") or asset.get("ticker")
        score = row.get("score") or ranking.get("context_score") or ranking.get("score")
        status = row.get("decision") or permission.get("status") or row.get("status")
        reason = row.get("guard") or row.get("decision_label") or row.get("reason") or ""
        rankings.append(
            {
                "rank_position": index,
                "ticker": _text(ticker, "-").upper(),
                "score": _float_or_none(score),
                "status": _text(status),
                "reason": _text(reason),
                "payload_json": _json_text(row),
            }
        )
    return rankings


def save_daily_run(payload: dict[str, Any], *, db_path: str | Path | None = None) -> int:
    created_at = _now_iso()
    init_db(db_path or DEFAULT_DB_PATH)
    daily_row = _daily_run_row(payload, created_at)
    with connect(db_path or DEFAULT_DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO daily_runs (
                schema_version, run_date, created_at, profile, list_name, status,
                reason, market, trend, model_quality, behavior, long_basket_status,
                actionable, watch, blocked, report_json, report_txt, basket_csv,
                run_dir, payload_json
            )
            VALUES (
                :schema_version, :run_date, :created_at, :profile, :list_name, :status,
                :reason, :market, :trend, :model_quality, :behavior, :long_basket_status,
                :actionable, :watch, :blocked, :report_json, :report_txt, :basket_csv,
                :run_dir, :payload_json
            )
            """,
            daily_row,
        )
        daily_run_id = int(cursor.lastrowid)
        for signal, reasons in _signals_from_payload(payload):
            signal["daily_run_id"] = daily_run_id
            signal["created_at"] = created_at
            signal_cursor = conn.execute(
                """
                INSERT INTO signals (
                    daily_run_id, created_at, ticker, bias, action, status, score,
                    signal_class, executable, borrow_status, permission, source,
                    payload_json
                )
                VALUES (
                    :daily_run_id, :created_at, :ticker, :bias, :action, :status,
                    :score, :signal_class, :executable, :borrow_status, :permission,
                    :source, :payload_json
                )
                """,
                signal,
            )
            signal_id = int(signal_cursor.lastrowid)
            conn.executemany(
                """
                INSERT INTO signal_reasons (signal_id, reason_type, reason)
                VALUES (?, ?, ?)
                """,
                [(signal_id, reason_type, reason) for reason_type, reason in reasons],
            )
        for ranking in _rankings_from_payload(payload):
            ranking["daily_run_id"] = daily_run_id
            conn.execute(
                """
                INSERT INTO rankings (
                    daily_run_id, rank_position, ticker, score, status, reason,
                    payload_json
                )
                VALUES (
                    :daily_run_id, :rank_position, :ticker, :score, :status,
                    :reason, :payload_json
                )
                """,
                ranking,
            )
        conn.commit()
    return daily_run_id


def save_simulation(
    summary: dict[str, Any],
    trades: list[dict[str, Any]] | None = None,
    *,
    db_path: str | Path | None = None,
) -> int:
    created_at = _now_iso()
    init_db(db_path or DEFAULT_DB_PATH)
    with connect(db_path or DEFAULT_DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO simulations (
                schema_version, created_at, name, status, summary_path, trades_csv,
                summary_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                SCHEMA_VERSION,
                created_at,
                _text(summary.get("name")),
                _text(summary.get("status")),
                _text(summary.get("summary_path")),
                _text(summary.get("trades_csv")),
                _json_text(summary),
            ),
        )
        simulation_id = int(cursor.lastrowid)
        trade_rows = []
        for index, trade in enumerate(trades or [], start=1):
            trade_rows.append(
                (
                    simulation_id,
                    index,
                    _text(trade.get("ticker")).upper(),
                    _text(trade.get("side")).upper(),
                    _text(trade.get("entry_date")),
                    _text(trade.get("exit_date")),
                    _float_or_none(trade.get("entry_price")),
                    _float_or_none(trade.get("exit_price")),
                    _float_or_none(trade.get("pnl")),
                    _float_or_none(trade.get("pnl_pct")),
                    _json_text(trade),
                )
            )
        conn.executemany(
            """
            INSERT INTO simulation_trades (
                simulation_id, trade_index, ticker, side, entry_date, exit_date,
                entry_price, exit_price, pnl, pnl_pct, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            trade_rows,
        )
        conn.commit()
    return simulation_id


def table_counts(*, db_path: str | Path | None = None) -> dict[str, int]:
    init_db(db_path or DEFAULT_DB_PATH)
    tables = [
        "daily_runs",
        "signals",
        "signal_reasons",
        "rankings",
        "simulations",
        "simulation_trades",
    ]
    with connect(db_path or DEFAULT_DB_PATH) as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])
            for table in tables
        }


def latest_daily_run(*, db_path: str | Path | None = None) -> dict[str, Any] | None:
    init_db(db_path or DEFAULT_DB_PATH)
    with connect(db_path or DEFAULT_DB_PATH) as conn:
        row = conn.execute(
            "SELECT * FROM daily_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def signals_for_ticker(
    ticker: str,
    *,
    limit: int = 20,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    init_db(db_path or DEFAULT_DB_PATH)
    normalized = _text(ticker).upper()
    with connect(db_path or DEFAULT_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT s.*, d.profile, d.list_name, d.run_date
            FROM signals s
            JOIN daily_runs d ON d.id = s.daily_run_id
            WHERE s.ticker = ?
            ORDER BY s.id DESC
            LIMIT ?
            """,
            (normalized, max(1, int(limit))),
        ).fetchall()
    return [dict(row) for row in rows]


def latest_rankings(*, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    init_db(db_path or DEFAULT_DB_PATH)
    with connect(db_path or DEFAULT_DB_PATH) as conn:
        latest = conn.execute("SELECT id FROM daily_runs ORDER BY id DESC LIMIT 1").fetchone()
        if not latest:
            return []
        rows = conn.execute(
            """
            SELECT *
            FROM rankings
            WHERE daily_run_id = ?
            ORDER BY rank_position ASC
            """,
            (int(latest["id"]),),
        ).fetchall()
    return [dict(row) for row in rows]


def latest_simulation(*, db_path: str | Path | None = None) -> dict[str, Any] | None:
    init_db(db_path or DEFAULT_DB_PATH)
    with connect(db_path or DEFAULT_DB_PATH) as conn:
        row = conn.execute(
            "SELECT * FROM simulations ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        trades = conn.execute(
            """
            SELECT *
            FROM simulation_trades
            WHERE simulation_id = ?
            ORDER BY trade_index ASC
            """,
            (int(row["id"]),),
        ).fetchall()
    payload = dict(row)
    payload["trades"] = [dict(trade) for trade in trades]
    return payload
