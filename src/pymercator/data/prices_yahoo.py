from __future__ import annotations

from pathlib import Path
from typing import Any

from pymercator.data.prices_csv import write_price_rows_csv
from pymercator.data.ticker_list import ticker_symbols_from_csv


def _safe_price_filename(ticker: str) -> str:
    return ticker.strip().upper().replace("/", "-").replace("\\", "-") + ".csv"


def _normalize_tickers(tickers: list[str]) -> list[str]:
    return [ticker.strip().upper() for ticker in tickers if ticker.strip()]


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
) -> dict[str, Any]:
    normalized_tickers = _normalize_tickers(tickers)
    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []

    for ticker in normalized_tickers:
        output_path = base / _safe_price_filename(ticker)

        try:
            rows = fetch_yahoo_prices(
                ticker=ticker,
                start=start,
                end=end,
            )
            write_price_rows_csv(output_path, rows)

            results.append(
                {
                    "ticker": ticker,
                    "valid": True,
                    "path": str(output_path),
                    "rows": len(rows),
                    "start_date": rows[0]["date"],
                    "end_date": rows[-1]["date"],
                    "error": "",
                }
            )

        except Exception as exc:
            results.append(
                {
                    "ticker": ticker,
                    "valid": False,
                    "path": str(output_path),
                    "rows": 0,
                    "start_date": None,
                    "end_date": None,
                    "error": str(exc),
                }
            )

    fetched = sum(1 for item in results if item["valid"])
    failed = len(results) - fetched

    return {
        "output_dir": str(base),
        "tickers": normalized_tickers,
        "requested": len(normalized_tickers),
        "fetched": fetched,
        "failed": failed,
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
) -> dict[str, Any]:
    tickers = ticker_symbols_from_csv(tickers_file)

    payload = fetch_yahoo_prices_to_dir(
        tickers=tickers,
        start=start,
        end=end,
        output_dir=output_dir,
    )
    payload["tickers_file"] = str(tickers_file)

    return payload

