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


def _read_cached_frame(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=list(PRICE_COLUMNS))

    try:
        rows = pd.read_csv(path)
    except Exception:
        return pd.DataFrame(columns=list(PRICE_COLUMNS))

    if rows.empty:
        return pd.DataFrame(columns=list(PRICE_COLUMNS))

    missing = [column for column in PRICE_COLUMNS if column not in rows.columns]
    if missing:
        return pd.DataFrame(columns=list(PRICE_COLUMNS))

    return _sanitize_ohlcv_rows(rows)


def _frame_span(rows: pd.DataFrame) -> tuple[str | None, str | None]:
    if rows.empty or "date" not in rows.columns:
        return None, None

    dates = sorted(str(item) for item in rows["date"].dropna().tolist())
    if not dates:
        return None, None

    return dates[0], dates[-1]


def _merge_frames(existing: pd.DataFrame, fetched: pd.DataFrame) -> pd.DataFrame:
    if existing.empty:
        return _sanitize_ohlcv_rows(fetched)

    if fetched.empty:
        return _sanitize_ohlcv_rows(existing)

    merged = pd.concat([existing, fetched], ignore_index=True)

    if merged.empty:
        return pd.DataFrame(columns=list(PRICE_COLUMNS))

    merged = _sanitize_ohlcv_rows(merged)
    merged = merged.sort_values("date").drop_duplicates("date", keep="last")
    return merged[list(PRICE_COLUMNS)]


def fetch_indices_prices(
    *,
    catalog: str | Path,
    start: str,
    output: str | Path,
    end: str | None = None,
    use_cache: bool = True,
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
        cached_rows = _read_cached_frame(output_path) if use_cache else pd.DataFrame()
        cached_start, cached_end = _frame_span(cached_rows)

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
            if use_cache and not cached_rows.empty and end and cached_end and cached_end >= end:
                results.append(
                    {
                        "name": item["name"],
                        "symbol": symbol,
                        "required": required,
                        "enabled": enabled,
                        "status": "CACHED",
                        "mode": "cache_hit",
                        "rows": len(cached_rows),
                        "start": cached_start or "",
                        "end": cached_end or "",
                        "path": str(output_path),
                        "error": "",
                    }
                )
                continue

            fetch_start = start
            if use_cache and not cached_rows.empty and cached_start and cached_end:
                fetch_start = start if start < cached_start else cached_end

            rows = _download_yfinance(symbol, start=fetch_start, end=end)
            rows = _sanitize_ohlcv_rows(rows) if not rows.empty else rows

            if rows.empty:
                if use_cache and not cached_rows.empty:
                    results.append(
                        {
                            "name": item["name"],
                            "symbol": symbol,
                            "required": required,
                            "enabled": enabled,
                            "status": "CACHE_FALLBACK",
                            "mode": "cache_fallback",
                            "rows": len(cached_rows),
                            "start": cached_start or "",
                            "end": cached_end or "",
                            "path": str(output_path),
                            "error": "empty download",
                        }
                    )
                    continue

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

            merged_rows = (
                _merge_frames(cached_rows, rows) if use_cache else rows
            )
            merged_start, merged_end = _frame_span(merged_rows)
            merged_rows.to_csv(output_path, index=False)

            mode = "fetched"
            if not use_cache:
                mode = "no_cache_fetch"
            elif not cached_rows.empty and cached_start and start < cached_start:
                mode = "backfilled"
            elif not cached_rows.empty:
                mode = "updated"

            results.append(
                {
                    "name": item["name"],
                    "symbol": symbol,
                    "required": required,
                    "enabled": enabled,
                    "status": "OK",
                    "mode": mode,
                    "rows": len(merged_rows),
                    "start": merged_start or "",
                    "end": merged_end or "",
                    "path": str(output_path),
                    "error": "",
                }
            )

        except Exception as exc:
            if use_cache and not cached_rows.empty:
                results.append(
                    {
                        "name": item["name"],
                        "symbol": symbol,
                        "required": required,
                        "enabled": enabled,
                        "status": "CACHE_FALLBACK",
                        "mode": "cache_fallback",
                        "rows": len(cached_rows),
                        "start": cached_start or "",
                        "end": cached_end or "",
                        "path": str(output_path),
                        "error": str(exc),
                    }
                )
                continue

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
    skipped = sum(1 for item in results if item["status"] == "SKIPPED")
    required_failed = sum(
        1 for item in results if item["status"] == "FAILED_REQUIRED"
    )
    optional_failed = sum(
        1 for item in results if item["status"] == "FAILED_OPTIONAL"
    )
    failed = required_failed + optional_failed
    warnings: list[str] = []
    for item in results:
        if item.get("status") == "FAILED_OPTIONAL":
            warnings.append(
                f"optional index {item.get('symbol', '-')} failed: {item.get('error', '-')}"
            )
        elif item.get("status") == "CACHE_FALLBACK":
            warnings.append(
                f"index {item.get('symbol', '-')} used cache fallback: {item.get('error', '-')}"
            )

    if required_failed:
        status = "FAILED"
    elif optional_failed or cache_fallbacks:
        status = "OK_WITH_WARNINGS"
    else:
        status = "OK"

    return {
        "catalog": str(catalog),
        "output": str(output_dir),
        "requested": len(results),
        "fetched": fetched,
        "updated": updated,
        "backfilled": backfilled,
        "cache_hits": cache_hits,
        "cache_fallbacks": cache_fallbacks,
        "no_cache_fetched": no_cache_fetched,
        "failed": failed,
        "required_failed": required_failed,
        "optional_failed": optional_failed,
        "skipped": skipped,
        "status": status,
        "use_cache": use_cache,
        "warnings": warnings,
        "start": start,
        "end": end,
        "results": results,
    }


def check_indices_prices_dir(prices_dir: str | Path) -> dict[str, Any]:
    return check_prices_dir(prices_dir)
