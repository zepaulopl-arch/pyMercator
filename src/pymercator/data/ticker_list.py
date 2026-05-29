from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

TICKER_COLUMNS = ("ticker", "sector")


STARTER_TICKERS = (
    {"ticker": "PETR4.SA", "sector": "OilGas"},
    {"ticker": "PRIO3.SA", "sector": "OilGas"},
    {"ticker": "VALE3.SA", "sector": "Mining"},
    {"ticker": "GGBR4.SA", "sector": "Steel"},
    {"ticker": "ITUB4.SA", "sector": "Banks"},
    {"ticker": "BBDC4.SA", "sector": "Banks"},
    {"ticker": "BBAS3.SA", "sector": "Banks"},
    {"ticker": "ABEV3.SA", "sector": "Consumer"},
    {"ticker": "LREN3.SA", "sector": "Retail"},
    {"ticker": "MGLU3.SA", "sector": "Retail"},
    {"ticker": "ASAI3.SA", "sector": "Retail"},
    {"ticker": "TOTS3.SA", "sector": "Tech"},
    {"ticker": "WEGE3.SA", "sector": "Industrial"},
    {"ticker": "SBSP3.SA", "sector": "Utilities"},
    {"ticker": "CMIG4.SA", "sector": "Utilities"},
    {"ticker": "BRAP4.SA", "sector": "Holding"},
)


def normalize_ticker(value: str) -> str:
    ticker = value.strip().upper()

    if not ticker:
        return ""

    if "." not in ticker:
        ticker = f"{ticker}.SA"

    return ticker


def read_ticker_list_csv(path: str | Path) -> list[dict[str, str]]:
    csv_path = Path(path)

    if not csv_path.exists():
        raise FileNotFoundError(f"Ticker list not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        rows = [dict(row) for row in reader]

    return rows


def validate_ticker_list_csv(path: str | Path) -> dict[str, Any]:
    csv_path = Path(path)

    if not csv_path.exists():
        return {
            "path": str(csv_path),
            "valid": False,
            "rows": 0,
            "missing_columns": list(TICKER_COLUMNS),
            "extra_columns": [],
            "duplicate_tickers": [],
            "row_errors": [
                {
                    "line": 0,
                    "field": "file",
                    "error": "file not found",
                }
            ],
        }

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]

    missing_columns = [column for column in TICKER_COLUMNS if column not in fieldnames]
    extra_columns = [column for column in fieldnames if column not in TICKER_COLUMNS]

    row_errors: list[dict[str, Any]] = []
    seen: set[str] = set()
    duplicates: set[str] = set()

    for index, row in enumerate(rows, start=2):
        ticker = normalize_ticker(row.get("ticker", ""))

        if not ticker:
            row_errors.append(
                {
                    "line": index,
                    "field": "ticker",
                    "error": "missing ticker",
                }
            )
            continue

        if ticker in seen:
            duplicates.add(ticker)
        else:
            seen.add(ticker)

        if not (row.get("sector") or "").strip():
            row_errors.append(
                {
                    "line": index,
                    "field": "sector",
                    "error": "missing sector",
                }
            )

    return {
        "path": str(csv_path),
        "valid": not missing_columns and not duplicates and not row_errors,
        "rows": len(rows),
        "missing_columns": missing_columns,
        "extra_columns": extra_columns,
        "duplicate_tickers": sorted(duplicates),
        "row_errors": row_errors,
    }


def ticker_symbols_from_csv(path: str | Path) -> list[str]:
    validation = validate_ticker_list_csv(path)

    if not validation["valid"]:
        raise ValueError(f"Invalid ticker list: {validation}")

    rows = read_ticker_list_csv(path)
    return [normalize_ticker(row["ticker"]) for row in rows]


def write_starter_ticker_list(path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=TICKER_COLUMNS)
        writer.writeheader()
        writer.writerows(STARTER_TICKERS)
