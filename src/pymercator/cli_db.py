from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pymercator.storage.db import DEFAULT_DB_PATH, init_db
from pymercator.storage.repositories import (
    latest_daily_run,
    latest_rankings,
    latest_simulation,
    signals_for_ticker,
    table_counts,
)
from pymercator.terminal_render import (
    render_empty_state,
    render_key_values,
    render_table,
)


def _db_path(args: Any) -> str:
    return str(getattr(args, "db", "") or DEFAULT_DB_PATH)


def _status_payload(db_path: str) -> dict[str, Any]:
    path = Path(db_path)
    existed = path.exists()
    init_db(path)
    counts = table_counts(db_path=path)
    return {
        "command": "db status",
        "path": str(path),
        "exists": path.exists(),
        "created": not existed and path.exists(),
        "tables": counts,
    }


def _render_status(payload: dict[str, Any]) -> str:
    tables = payload.get("tables", {})
    return render_key_values(
        "DB STATUS",
        [
            ("path", payload.get("path", "-")),
            ("exists", "YES" if payload.get("exists") else "NO"),
            ("created", "YES" if payload.get("created") else "NO"),
            ("daily_runs", tables.get("daily_runs", 0)),
            ("signals", tables.get("signals", 0)),
            ("signal_reasons", tables.get("signal_reasons", 0)),
            ("rankings", tables.get("rankings", 0)),
            ("simulations", tables.get("simulations", 0)),
            ("simulation_trades", tables.get("simulation_trades", 0)),
        ],
    )


def _render_last_run(row: dict[str, Any] | None) -> str:
    if not row:
        return render_empty_state("DB LAST RUN", reason="no daily runs stored")
    return render_key_values(
        "DB LAST RUN",
        [
            ("id", row.get("id", "-")),
            ("run_date", row.get("run_date", "-")),
            ("created_at", row.get("created_at", "-")),
            ("profile", row.get("profile", "-")),
            ("list", row.get("list_name", "-")),
            ("status", row.get("status", "-"), row.get("status", "-")),
            ("market", row.get("market", "-"), row.get("market", "-")),
            ("trend", row.get("trend", "-"), row.get("trend", "-")),
            ("model_quality", row.get("model_quality", "-"), row.get("model_quality", "-")),
            ("behavior", row.get("behavior", "-"), row.get("behavior", "-")),
            ("basket", row.get("long_basket_status", "-"), row.get("long_basket_status", "-")),
            ("actionable", row.get("actionable", 0)),
            ("watch", row.get("watch", 0)),
            ("blocked", row.get("blocked", 0)),
            ("report_json", row.get("report_json", "-")),
            ("basket_csv", row.get("basket_csv", "-")),
        ],
    )


def _render_signals(ticker: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return render_empty_state(
            f"DB SIGNAL {ticker.upper()}",
            reason="no signals stored for ticker",
        )
    return render_table(
        f"DB SIGNAL {ticker.upper()}",
        ["#", "DATE", "PROFILE", "BIAS", "STATUS", "SCORE", "CLASS", "SOURCE"],
        [
            (
                index,
                row.get("run_date", "-"),
                row.get("profile", "-"),
                row.get("bias", "-"),
                row.get("status", "-"),
                "-" if row.get("score") is None else f"{float(row['score']):.2f}",
                row.get("signal_class", "-"),
                row.get("source", "-"),
            )
            for index, row in enumerate(rows, start=1)
        ],
        widths=[3, 10, 7, 6, 12, 8, 18, 18],
    )


def _render_rankings(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return render_empty_state("DB RANK LAST", reason="no rankings stored")
    return render_table(
        "DB RANK LAST",
        ["#", "TICKER", "SCORE", "STATUS", "REASON"],
        [
            (
                row.get("rank_position", index),
                row.get("ticker", "-"),
                "-" if row.get("score") is None else f"{float(row['score']):.2f}",
                row.get("status", "-"),
                row.get("reason", "-"),
            )
            for index, row in enumerate(rows, start=1)
        ],
        widths=[3, 8, 8, 12, 36],
    )


def _render_simulation(row: dict[str, Any] | None) -> str:
    if not row:
        return render_empty_state("DB SIM LAST", reason="no simulations stored")
    return render_key_values(
        "DB SIM LAST",
        [
            ("id", row.get("id", "-")),
            ("created_at", row.get("created_at", "-")),
            ("name", row.get("name", "-")),
            ("status", row.get("status", "-"), row.get("status", "-")),
            ("trades", len(row.get("trades", []))),
            ("summary_path", row.get("summary_path", "-")),
            ("trades_csv", row.get("trades_csv", "-")),
        ],
    )


def run_db_command(args: Any) -> int:
    command = getattr(args, "db_command", "") or "status"
    db_path = _db_path(args)

    if command == "status":
        payload = _status_payload(db_path)
        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_render_status(payload))
        return 0

    if command == "last-run":
        payload = latest_daily_run(db_path=db_path)
        if getattr(args, "json", False):
            print(json.dumps(payload or {}, ensure_ascii=False, indent=2))
        else:
            print(_render_last_run(payload))
        return 0 if payload else 1

    if command == "signal":
        ticker = getattr(args, "ticker", "")
        payload = signals_for_ticker(
            ticker,
            limit=getattr(args, "limit", 20),
            db_path=db_path,
        )
        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_render_signals(ticker, payload))
        return 0 if payload else 1

    if command == "rank-last":
        payload = latest_rankings(db_path=db_path)
        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_render_rankings(payload))
        return 0 if payload else 1

    if command == "sim-last":
        payload = latest_simulation(db_path=db_path)
        if getattr(args, "json", False):
            print(json.dumps(payload or {}, ensure_ascii=False, indent=2))
        else:
            print(_render_simulation(payload))
        return 0 if payload else 1

    raise ValueError(f"unknown db command: {command}")
