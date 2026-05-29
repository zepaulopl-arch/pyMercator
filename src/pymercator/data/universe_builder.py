from __future__ import annotations

import csv
from math import sqrt
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from pymercator.data.prices_csv import read_price_rows_csv
from pymercator.data.ticker_list import normalize_ticker, read_ticker_list_csv
from pymercator.data.universe_csv import REQUIRED_COLUMNS
from pymercator.sentiment_store import load_news_scores

DEFAULT_SECTOR = "UNKNOWN"
DEFAULT_QUALITY_SCORE = 50.0
DEFAULT_NEWS_SCORE = 50.0


SECTOR_MAP = {
    "PRIO3": "OilGas",
    "PETR4": "OilGas",
    "PETR3": "OilGas",
    "VALE3": "Mining",
    "GGBR4": "Steel",
    "CSNA3": "Steel",
    "USIM5": "Steel",
    "ITUB4": "Banks",
    "BBDC4": "Banks",
    "BBAS3": "Banks",
    "SANB11": "Banks",
    "ABEV3": "Consumer",
    "LREN3": "Retail",
    "MGLU3": "Retail",
    "ASAI3": "Retail",
    "TOTS3": "Tech",
    "WEGE3": "Industrial",
    "SBSP3": "Utilities",
    "CMIG4": "Utilities",
    "BRAP4": "Holding",
}


def _base_ticker(filename: str) -> str:
    stem = Path(filename).stem.upper()
    if stem.endswith(".SA"):
        stem = stem[:-3]
    return stem


def _base_from_symbol(symbol: str) -> str:
    ticker = normalize_ticker(symbol)
    if ticker.endswith(".SA"):
        return ticker[:-3]
    return ticker


def load_sector_map_from_ticker_file(path: str | Path | None) -> dict[str, str]:
    if not path:
        return {}

    rows = read_ticker_list_csv(path)
    sector_map: dict[str, str] = {}

    for row in rows:
        ticker = _base_from_symbol(row.get("ticker", ""))
        sector = (row.get("sector") or "").strip()

        if ticker and sector:
            sector_map[ticker] = sector

    return sector_map


def _to_float(value: str | float | int) -> float:
    return float(value)


def _load_price_rows(path: str | Path) -> list[dict[str, Any]]:
    rows = read_price_rows_csv(path)

    parsed: list[dict[str, Any]] = []
    for row in rows:
        parsed.append(
            {
                "date": row["date"],
                "open": _to_float(row["open"]),
                "high": _to_float(row["high"]),
                "low": _to_float(row["low"]),
                "close": _to_float(row["close"]),
                "volume": _to_float(row["volume"]),
            }
        )

    parsed.sort(key=lambda item: item["date"])
    return parsed


def _score_from_ratio(value: float, low: float, high: float) -> float:
    if high <= low:
        return 50.0

    score = ((value - low) / (high - low)) * 100.0
    return round(max(0.0, min(100.0, score)), 2)


def _trend_score(closes: list[float]) -> float:
    if len(closes) < 60:
        return 50.0

    last = closes[-1]
    ma_20 = mean(closes[-20:])
    ma_60 = mean(closes[-60:])

    ratio = ((last / ma_20) - 1.0) * 0.55 + ((ma_20 / ma_60) - 1.0) * 0.45
    return _score_from_ratio(ratio, -0.12, 0.12)


def _momentum_score(closes: list[float]) -> float:
    if len(closes) < 22:
        return 50.0

    last = closes[-1]
    prev = closes[-22]
    momentum = (last / prev) - 1.0

    return _score_from_ratio(momentum, -0.15, 0.15)


def _daily_returns(closes: list[float]) -> list[float]:
    returns: list[float] = []

    for index in range(1, len(closes)):
        previous = closes[index - 1]
        current = closes[index]

        if previous <= 0:
            continue

        returns.append((current / previous) - 1.0)

    return returns


def _volatility_pct(closes: list[float], window: int = 21) -> float:
    returns = _daily_returns(closes)[-window:]

    if len(returns) < 2:
        return 0.0

    daily_std = pstdev(returns)
    annualized = daily_std * sqrt(252.0)

    return round(annualized * 100.0, 2)


def _atr_pct(rows: list[dict[str, Any]], window: int = 14) -> float:
    if len(rows) < 2:
        return 0.0

    true_ranges: list[float] = []

    for index in range(1, len(rows)):
        current = rows[index]
        previous = rows[index - 1]
        previous_close = previous["close"]

        tr = max(
            current["high"] - current["low"],
            abs(current["high"] - previous_close),
            abs(current["low"] - previous_close),
        )
        true_ranges.append(tr)

    recent = true_ranges[-window:]

    if not recent:
        return 0.0

    last_close = rows[-1]["close"]
    if last_close <= 0:
        return 0.0

    atr = mean(recent)
    return round((atr / last_close) * 100.0, 2)


def _avg_volume_brl(rows: list[dict[str, Any]], window: int = 21) -> float:
    recent = rows[-window:]

    if not recent:
        return 0.0

    values = [row["close"] * row["volume"] for row in recent]
    return round(mean(values), 2)


def _liquidity_score(avg_volume_brl: float) -> float:
    if avg_volume_brl >= 500_000_000:
        return 100.0
    if avg_volume_brl >= 250_000_000:
        return 90.0
    if avg_volume_brl >= 100_000_000:
        return 80.0
    if avg_volume_brl >= 50_000_000:
        return 65.0
    if avg_volume_brl >= 10_000_000:
        return 50.0
    return 25.0


def _trade_plan(rows: list[dict[str, Any]]) -> tuple[float, float, float]:
    last_close = rows[-1]["close"]
    atr_percentage = _atr_pct(rows)

    stop_distance = max(last_close * 0.02, last_close * (atr_percentage / 100.0))
    target_distance = stop_distance * 1.6

    entry = last_close
    stop = last_close - stop_distance
    target = last_close + target_distance

    return round(entry, 2), round(stop, 2), round(target, 2)



def _news_score_for_ticker(
    news_scores: dict[str, dict[str, Any]] | None,
    ticker: str,
) -> float:
    if not news_scores:
        return DEFAULT_NEWS_SCORE

    ticker_text = ticker.upper()
    candidates = [ticker_text]

    if not ticker_text.endswith(".SA"):
        candidates.append(f"{ticker_text}.SA")

    for candidate in candidates:
        payload = news_scores.get(candidate)
        if payload:
            return float(payload.get("news_score", DEFAULT_NEWS_SCORE))

    return DEFAULT_NEWS_SCORE


def build_asset_from_price_file(
    path: str | Path,
    sector_map: dict[str, str] | None = None,
    news_scores: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    price_path = Path(path)
    rows = _load_price_rows(price_path)

    if len(rows) < 30:
        raise ValueError(f"Not enough price rows for {price_path.name}: {len(rows)}")

    ticker = _base_ticker(price_path.name)
    sectors = sector_map or {}
    closes = [row["close"] for row in rows]
    avg_volume = _avg_volume_brl(rows)
    volatility = _volatility_pct(closes)
    atr = _atr_pct(rows)
    entry, stop, target = _trade_plan(rows)

    return {
        "ticker": ticker,
        "sector": sectors.get(ticker, SECTOR_MAP.get(ticker, DEFAULT_SECTOR)),
        "last_close": round(closes[-1], 2),
        "avg_volume_brl": round(avg_volume, 2),
        "trend_score": _trend_score(closes),
        "momentum_score": _momentum_score(closes),
        "volatility_pct": volatility,
        "atr_pct": atr,
        "liquidity_score": _liquidity_score(avg_volume),
        "quality_score": DEFAULT_QUALITY_SCORE,
        "news_score": _news_score_for_ticker(news_scores, ticker),
        "entry": entry,
        "stop": stop,
        "target": target,
    }


def build_universe_from_prices_dir(
    prices_dir: str | Path,
    tickers_file: str | Path | None = None,
    sentiment_dir: str | Path | None = None,
) -> dict[str, Any]:
    base = Path(prices_dir)

    if not base.exists():
        raise FileNotFoundError(f"Prices directory not found: {base}")

    sector_map = load_sector_map_from_ticker_file(tickers_file)
    sentiment_tickers = [
        f"{_base_ticker(file_path.name)}.SA"
        for file_path in sorted(base.glob("*.csv"))
    ]
    news_scores = (
        load_news_scores(
            sentiment_dir=sentiment_dir,
            tickers=sentiment_tickers,
        )
        if sentiment_dir
        else {}
    )

    assets: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for file_path in sorted(base.glob("*.csv")):
        try:
            assets.append(
                build_asset_from_price_file(
                    file_path,
                    sector_map=sector_map,
                    news_scores=news_scores,
                )
            )
        except Exception as exc:
            errors.append(
                {
                    "file": str(file_path),
                    "error": str(exc),
                }
            )

    assets.sort(key=lambda item: item["ticker"])

    return {
        "prices_dir": str(base),
        "tickers_file": str(tickers_file) if tickers_file else "",
        "assets": assets,
        "errors": errors,
        "asset_count": len(assets),
        "error_count": len(errors),
    }


def write_universe_csv(path: str | Path, assets: list[dict[str, Any]]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()

        for asset in assets:
            writer.writerow({column: asset[column] for column in REQUIRED_COLUMNS})


def build_universe_csv_from_prices(
    *,
    prices_dir: str | Path,
    output: str | Path,
    tickers_file: str | Path | None = None,
    sentiment_dir: str | Path | None = None,
) -> dict[str, Any]:
    payload = build_universe_from_prices_dir(
        prices_dir,
        tickers_file=tickers_file,
        sentiment_dir=sentiment_dir,
    )
    write_universe_csv(output, payload["assets"])

    return {
        "prices_dir": payload["prices_dir"],
        "tickers_file": payload["tickers_file"],
        "output": str(output),
        "asset_count": payload["asset_count"],
        "error_count": payload["error_count"],
        "errors": payload["errors"],
        "assets": payload["assets"],
    }
