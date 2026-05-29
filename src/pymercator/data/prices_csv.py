from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

PRICE_COLUMNS = (
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
)


def _parse_float(value: str) -> float:
    text = (value or "").strip()
    if not text:
        raise ValueError("empty numeric value")
    return float(text)


def _parse_date(value: str) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError("empty date")

    parsed = datetime.fromisoformat(text)
    return parsed.date().isoformat()


def write_price_rows_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=PRICE_COLUMNS)
        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    "date": row["date"],
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row["volume"],
                }
            )


def read_price_rows_csv(path: str | Path) -> list[dict[str, str]]:
    csv_path = Path(path)

    if not csv_path.exists():
        raise FileNotFoundError(f"Price file not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return [dict(row) for row in reader]


def price_fieldnames(path: str | Path) -> list[str]:
    csv_path = Path(path)

    if not csv_path.exists():
        raise FileNotFoundError(f"Price file not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader.fieldnames or [])


def validate_price_csv(path: str | Path) -> dict[str, Any]:
    csv_path = Path(path)
    fieldnames = price_fieldnames(csv_path)
    rows = read_price_rows_csv(csv_path)

    missing_columns = [column for column in PRICE_COLUMNS if column not in fieldnames]
    extra_columns = [column for column in fieldnames if column not in PRICE_COLUMNS]

    row_errors: list[dict[str, Any]] = []
    dates_seen: set[str] = set()
    duplicate_dates: set[str] = set()
    parsed_dates: list[str] = []

    numeric_columns = ("open", "high", "low", "close", "volume")

    for index, row in enumerate(rows, start=2):
        date_value = row.get("date", "")

        try:
            parsed_date = _parse_date(date_value)
            parsed_dates.append(parsed_date)

            if parsed_date in dates_seen:
                duplicate_dates.add(parsed_date)
            else:
                dates_seen.add(parsed_date)

        except ValueError as exc:
            row_errors.append(
                {
                    "line": index,
                    "field": "date",
                    "error": str(exc),
                }
            )

        for column in numeric_columns:
            value = row.get(column, "")

            try:
                parsed = _parse_float(value)
            except ValueError as exc:
                row_errors.append(
                    {
                        "line": index,
                        "field": column,
                        "error": str(exc),
                    }
                )
                continue

            if column != "volume" and parsed <= 0:
                row_errors.append(
                    {
                        "line": index,
                        "field": column,
                        "error": "price must be positive",
                    }
                )

            if column == "volume" and parsed < 0:
                row_errors.append(
                    {
                        "line": index,
                        "field": column,
                        "error": "volume cannot be negative",
                    }
                )

    return {
        "path": str(csv_path),
        "valid": not missing_columns and not row_errors and not duplicate_dates,
        "rows": len(rows),
        "columns": fieldnames,
        "required_columns": list(PRICE_COLUMNS),
        "missing_columns": missing_columns,
        "extra_columns": extra_columns,
        "duplicate_dates": sorted(duplicate_dates),
        "row_errors": row_errors,
        "start_date": min(parsed_dates) if parsed_dates else None,
        "end_date": max(parsed_dates) if parsed_dates else None,
    }


def check_prices_dir(prices_dir: str | Path) -> dict[str, Any]:
    base = Path(prices_dir)

    if not base.exists():
        return {
            "prices_dir": str(base),
            "exists": False,
            "files": 0,
            "valid_files": 0,
            "invalid_files": 0,
            "results": [],
        }

    results = []

    for file_path in sorted(base.glob("*.csv")):
        try:
            result = validate_price_csv(file_path)
        except Exception as exc:
            result = {
                "path": str(file_path),
                "valid": False,
                "rows": 0,
                "start_date": None,
                "end_date": None,
                "error": str(exc),
            }

        results.append(result)

    valid_files = sum(1 for item in results if item.get("valid") is True)
    invalid_files = len(results) - valid_files

    return {
        "prices_dir": str(base),
        "exists": True,
        "files": len(results),
        "valid_files": valid_files,
        "invalid_files": invalid_files,
        "results": results,
    }
