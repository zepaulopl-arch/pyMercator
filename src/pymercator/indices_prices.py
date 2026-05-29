from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from pymercator.data.prices_csv import check_prices_dir
from pymercator.indices_catalog import read_indices_catalog

PRICE_COLUMNS = ("date", "open", "high", "low", "close", "volume")


def _safe_filename(symbol: str) -> str:
    return (
        symbol.strip()
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
    )


def _sanitize_ohlcv_rows(rows: pd.DataFrame) -> pd.DataFrame:
    rows = rows.copy()

    rows = rows.dropna(subset=["date", "close"])

    numeric_columns = ["open", "high", "low", "close", "volume"]
    for column in numeric_columns:
        rows[column] = pd.to_numeric(rows[column], errors="coerce")

    rows = rows.dropna(subset=["close"])
    rows = rows[rows["close"] > 0]

    for column in ("open", "high", "low"):
        rows.loc[rows[column].isna() | (rows[column] <= 0), column] = rows["close"]

    rows["volume"] = rows["volume"].fillna(0)

    return rows[list(PRICE_COLUMNS)]


def _download_yfinance(symbol: str, start: str, end: str | None = None) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance is not installed. Run: python -m pip install -e .") from exc

    data = yf.download(
        symbol,
        start=start,
        end=end,
        progress=False,
        auto_adjust=False,
        threads=False,
    )

    if data is None or data.empty:
        return pd.DataFrame()

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [str(column[0]).lower() for column in data.columns]
    else:
        data.columns = [str(column).lower() for column in data.columns]

    data = data.reset_index()
    data.columns = [str(column).lower() for column in data.columns]

    date_column = "date"
    if "datetime" in data.columns:
        date_column = "datetime"

    rows = pd.DataFrame(
        {
            "date": pd.to_datetime(data[date_column]).dt.date.astype(str),
            "open": data.get("open", data.get("close")),
            "high": data.get("high", data.get("close")),
            "low": data.get("low", data.get("close")),
            "close": data.get("close"),
            "volume": data.get("volume", 0),
        }
    )

    return _sanitize_ohlcv_rows(rows)


def fetch_indices_prices(
    *,
    catalog: str | Path,
    start: str,
    output: str | Path,
    end: str | None = None,
) -> dict[str, Any]:
    catalog_payload = read_indices_catalog(catalog)
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []

    for item in catalog_payload["indices"]:
        symbol = item["symbol"]
        required = bool(item.get("required", True))
        enabled = bool(item.get("enabled", True))
        filename = f"{_safe_filename(symbol)}.csv"
        output_path = output_dir / filename

        if not enabled:
            results.append(
                {
                    "name": item["name"],
                    "symbol": symbol,
                    "required": required,
                    "enabled": enabled,
                    "status": "SKIPPED",
                    "rows": 0,
                    "start": "",
                    "end": "",
                    "path": str(output_path),
                    "error": "disabled in catalog",
                }
            )
            continue

        try:
            rows = _download_yfinance(symbol, start=start, end=end)
            rows = _sanitize_ohlcv_rows(rows) if not rows.empty else rows

            if rows.empty:
                results.append(
                    {
                        "name": item["name"],
                        "symbol": symbol,
                        "required": required,
                        "enabled": enabled,
                        "status": "FAILED_REQUIRED" if required else "FAILED_OPTIONAL",
                        "rows": 0,
                        "start": "",
                        "end": "",
                        "path": str(output_path),
                        "error": "empty download",
                    }
                )
                continue

            rows.to_csv(output_path, index=False)

            results.append(
                {
                    "name": item["name"],
                    "symbol": symbol,
                    "required": required,
                    "enabled": enabled,
                    "status": "OK",
                    "rows": len(rows),
                    "start": str(rows["date"].iloc[0]),
                    "end": str(rows["date"].iloc[-1]),
                    "path": str(output_path),
                    "error": "",
                }
            )

        except Exception as exc:
            results.append(
                {
                    "name": item["name"],
                    "symbol": symbol,
                    "required": required,
                    "enabled": enabled,
                    "status": "FAILED_REQUIRED" if required else "FAILED_OPTIONAL",
                    "rows": 0,
                    "start": "",
                    "end": "",
                    "path": str(output_path),
                    "error": str(exc),
                }
            )

    fetched = sum(1 for item in results if item["status"] == "OK")
    skipped = sum(1 for item in results if item["status"] == "SKIPPED")
    required_failed = sum(
        1 for item in results if item["status"] == "FAILED_REQUIRED"
    )
    optional_failed = sum(
        1 for item in results if item["status"] == "FAILED_OPTIONAL"
    )
    failed = required_failed + optional_failed

    if required_failed:
        status = "FAILED"
    elif optional_failed:
        status = "OK_WITH_WARNINGS"
    else:
        status = "OK"

    return {
        "catalog": str(catalog),
        "output": str(output_dir),
        "requested": len(results),
        "fetched": fetched,
        "failed": failed,
        "required_failed": required_failed,
        "optional_failed": optional_failed,
        "skipped": skipped,
        "status": status,
        "start": start,
        "end": end,
        "results": results,
    }


def check_indices_prices_dir(prices_dir: str | Path) -> dict[str, Any]:
    return check_prices_dir(prices_dir)
