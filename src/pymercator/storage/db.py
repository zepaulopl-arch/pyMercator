from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

DEFAULT_DB_PATH = Path("data/aurum.db")

SCHEMA_VERSION = "aurum_storage.v1"

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS daily_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schema_version TEXT NOT NULL,
    run_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    profile TEXT NOT NULL,
    list_name TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    market TEXT NOT NULL DEFAULT '',
    trend TEXT NOT NULL DEFAULT '',
    model_quality TEXT NOT NULL DEFAULT '',
    behavior TEXT NOT NULL DEFAULT '',
    long_basket_status TEXT NOT NULL DEFAULT '',
    actionable INTEGER NOT NULL DEFAULT 0,
    watch INTEGER NOT NULL DEFAULT 0,
    blocked INTEGER NOT NULL DEFAULT 0,
    report_json TEXT NOT NULL DEFAULT '',
    report_txt TEXT NOT NULL DEFAULT '',
    basket_csv TEXT NOT NULL DEFAULT '',
    run_dir TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    daily_run_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    ticker TEXT NOT NULL,
    bias TEXT NOT NULL,
    action TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    score REAL,
    signal_class TEXT NOT NULL DEFAULT '',
    executable INTEGER NOT NULL DEFAULT 0,
    borrow_status TEXT NOT NULL DEFAULT '',
    permission TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL,
    FOREIGN KEY (daily_run_id) REFERENCES daily_runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS signal_reasons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL,
    reason_type TEXT NOT NULL,
    reason TEXT NOT NULL,
    FOREIGN KEY (signal_id) REFERENCES signals(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rankings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    daily_run_id INTEGER NOT NULL,
    rank_position INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    score REAL,
    status TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL,
    FOREIGN KEY (daily_run_id) REFERENCES daily_runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS simulations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schema_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    summary_path TEXT NOT NULL DEFAULT '',
    trades_csv TEXT NOT NULL DEFAULT '',
    summary_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS simulation_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    simulation_id INTEGER NOT NULL,
    trade_index INTEGER NOT NULL,
    ticker TEXT NOT NULL DEFAULT '',
    side TEXT NOT NULL DEFAULT '',
    entry_date TEXT NOT NULL DEFAULT '',
    exit_date TEXT NOT NULL DEFAULT '',
    entry_price REAL,
    exit_price REAL,
    pnl REAL,
    pnl_pct REAL,
    payload_json TEXT NOT NULL,
    FOREIGN KEY (simulation_id) REFERENCES simulations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_daily_runs_created_at ON daily_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_daily_runs_profile ON daily_runs(profile);
CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker);
CREATE INDEX IF NOT EXISTS idx_signals_daily_run_id ON signals(daily_run_id);
CREATE INDEX IF NOT EXISTS idx_rankings_daily_run_id ON rankings(daily_run_id);
CREATE INDEX IF NOT EXISTS idx_simulations_created_at ON simulations(created_at);
"""


def resolve_db_path(path: str | Path | None = None) -> Path:
    return Path(path) if path else DEFAULT_DB_PATH


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    db_path = resolve_db_path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: str | Path | None = None) -> Path:
    db_path = resolve_db_path(path)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
    return db_path


def iter_table_names(path: str | Path | None = None) -> Iterator[str]:
    init_db(path)
    with connect(path) as conn:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    for row in rows:
        yield str(row["name"])
