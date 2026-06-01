from __future__ import annotations

import contextlib
import io
from pathlib import Path
from typing import Any

from pymercator.data.prices_csv import read_price_rows_csv, write_price_rows_csv
from pymercator.data.ticker_list import ticker_symbols_from_csv


def _safe_price_filename(ticker: str) -> str:
    return ticker.strip().upper().replace("/", "-").replace("\\", "-") + ".csv"


def _normalize_tickers(tickers: list[str]) -> list[str]:
    return [ticker.strip().upper() for ticker in tickers if ticker.strip()]


def _read_cached_price_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    try:
        return list(read_price_rows_csv(path))
    except Exception:
        return []


def _merge_price_rows(
    existing_rows: list[dict[str, Any]],
    fetched_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows_by_date: dict[str, dict[str, Any]] = {}

    for row in [*existing_rows, *fetched_rows]:
        row_date = str(row.get("date", "")).strip()

        if not row_date:
            continue

        rows_by_date[row_date] = {
            "date": row_date,
            "open": row.get("open", ""),
            "high": row.get("high", ""),
            "low": row.get("low", ""),
            "close": row.get("close", ""),
            "volume": row.get("volume", 0),
        }

    return [rows_by_date[row_date] for row_date in sorted(rows_by_date)]


def _date_span(rows: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    dates = sorted(
        str(row.get("date", "")).strip()
        for row in rows
        if str(row.get("date", "")).strip()
    )

    if not dates:
        return None, None

    return dates[0], dates[-1]


def fetch_yahoo_prices(
    *,
    ticker: str,
    start: str,
    end: str | None = None,
) -> list[dict[str, Any]]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError(
            "yfinance is not installed. Run: python -m pip install -e ."
        ) from exc

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        data = yf.download(
            ticker,
            start=start,
            end=end,
            auto_adjust=False,
            progress=False,
            threads=False,
        )

    if data.empty:
        raise ValueError(f"No price data returned for ticker: {ticker}")

    if hasattr(data.columns, "nlevels") and data.columns.nlevels > 1:
        data.columns = data.columns.get_level_values(0)

    required = ("Open", "High", "Low", "Close", "Volume")
    missing = [column for column in required if column not in data.columns]

    if missing:
        raise ValueError(f"Missing Yahoo columns for {ticker}: {missing}")

    rows: list[dict[str, Any]] = []

    for index, row in data.iterrows():
        if row[["Open", "High", "Low", "Close"]].isna().any():
            continue

        volume = row["Volume"]
        if volume != volume:
            volume = 0

        rows.append(
            {
                "date": index.date().isoformat(),
                "open": round(float(row["Open"]), 6),
                "high": round(float(row["High"]), 6),
                "low": round(float(row["Low"]), 6),
                "close": round(float(row["Close"]), 6),
                "volume": int(volume),
            }
        )

    if not rows:
        raise ValueError(f"No valid OHLCV rows for ticker: {ticker}")

    return rows


def fetch_yahoo_prices_to_dir(
    *,
    tickers: list[str],
    start: str,
    output_dir: str | Path,
    end: str | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    normalized_tickers = _normalize_tickers(tickers)
    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []

    for ticker in normalized_tickers:
        output_path = base / _safe_price_filename(ticker)
        cached_rows = _read_cached_price_rows(output_path) if use_cache else []
        cached_start, cached_end = _date_span(cached_rows)

        try:
            if use_cache and cached_rows and end and cached_end and cached_end >= end:
                results.append(
                    {
                        "ticker": ticker,
                        "valid": True,
                        "status": "CACHED",
                        "mode": "cache_hit",
                        "path": str(output_path),
                        "rows": len(cached_rows),
                        "start_date": cached_start,
                        "end_date": cached_end,
                        "error": "",
                    }
                )
                continue

            fetch_start = start
            if use_cache and cached_rows and cached_start and cached_end:
                fetch_start = start if start < cached_start else cached_end

            rows = fetch_yahoo_prices(
                ticker=ticker,
                start=fetch_start,
                end=end,
            )
            merged_rows = (
                _merge_price_rows(cached_rows, rows) if use_cache else rows
            )
            merged_start, merged_end = _date_span(merged_rows)
            write_price_rows_csv(output_path, merged_rows)

            mode = "fetched"
            if not use_cache:
                mode = "no_cache_fetch"
            elif cached_rows and cached_start and start < cached_start:
                mode = "backfilled"
            elif cached_rows:
                mode = "updated"

            results.append(
                {
                    "ticker": ticker,
                    "valid": True,
                    "status": "OK",
                    "mode": mode,
                    "path": str(output_path),
                    "rows": len(merged_rows),
                    "start_date": merged_start,
                    "end_date": merged_end,
                    "error": "",
                }
            )

        except Exception as exc:
            if use_cache and cached_rows:
                results.append(
                    {
                        "ticker": ticker,
                        "valid": True,
                        "status": "CACHE_FALLBACK",
                        "mode": "cache_fallback",
                        "path": str(output_path),
                        "rows": len(cached_rows),
                        "start_date": cached_start,
                        "end_date": cached_end,
                        "error": str(exc),
                    }
                )
                continue

            results.append(
                {
                    "ticker": ticker,
                    "valid": False,
                    "status": "FAILED",
                    "mode": "failed",
                    "path": str(output_path),
                    "rows": 0,
                    "start_date": None,
                    "end_date": None,
                    "error": str(exc),
                }
            )

    fetched = sum(
        1
        for item in results
        if item.get("mode") in {"fetched", "no_cache_fetch"}
    )
    updated = sum(1 for item in results if item.get("mode") == "updated")
    backfilled = sum(1 for item in results if item.get("mode") == "backfilled")
    cache_hits = sum(1 for item in results if item.get("mode") == "cache_hit")
    cache_fallbacks = sum(
        1 for item in results if item.get("mode") == "cache_fallback"
    )
    no_cache_fetched = sum(
        1 for item in results if item.get("mode") == "no_cache_fetch"
    )
    available = sum(1 for item in results if item.get("valid") is True)
    failed = len(results) - available

    return {
        "output_dir": str(base),
        "tickers": normalized_tickers,
        "requested": len(normalized_tickers),
        "fetched": fetched,
        "updated": updated,
        "backfilled": backfilled,
        "cache_hits": cache_hits,
        "cache_fallbacks": cache_fallbacks,
        "no_cache_fetched": no_cache_fetched,
        "available": available,
        "failed": failed,
        "required_failed": failed,
        "use_cache": use_cache,
        "start": start,
        "end": end,
        "results": results,
    }

def fetch_yahoo_prices_from_ticker_file(
    *,
    tickers_file: str | Path,
    start: str,
    output_dir: str | Path,
    end: str | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    tickers = ticker_symbols_from_csv(tickers_file)

    payload = fetch_yahoo_prices_to_dir(
        tickers=tickers,
        start=start,
        end=end,
        output_dir=output_dir,
        use_cache=use_cache,
    )
    payload["tickers_file"] = str(tickers_file)

    return payload

