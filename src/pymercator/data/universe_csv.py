from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

from pymercator.domain import AssetSnapshot

REQUIRED_COLUMNS = (
    "ticker",
    "sector",
    "last_close",
    "avg_volume_brl",
    "trend_score",
    "momentum_score",
    "volatility_pct",
    "atr_pct",
    "liquidity_score",
    "quality_score",
    "news_score",
    "entry",
    "stop",
    "target",
)


TEMPLATE_ROWS = (
    {
        "ticker": "PRIO3",
        "sector": "OilGas",
        "last_close": "42.10",
        "avg_volume_brl": "250000000",
        "trend_score": "78",
        "momentum_score": "72",
        "volatility_pct": "5.2",
        "atr_pct": "4.1",
        "liquidity_score": "92",
        "quality_score": "60",
        "news_score": "45",
        "entry": "42.10",
        "stop": "40.80",
        "target": "44.40",
    },
    {
        "ticker": "VALE3",
        "sector": "Mining",
        "last_close": "62.30",
        "avg_volume_brl": "800000000",
        "trend_score": "63",
        "momentum_score": "58",
        "volatility_pct": "4.1",
        "atr_pct": "3.5",
        "liquidity_score": "95",
        "quality_score": "74",
        "news_score": "48",
        "entry": "62.30",
        "stop": "60.50",
        "target": "65.40",
    },
)


def _float(value: str, *, default: float = 0.0) -> float:
    text = (value or "").strip()
    if not text:
        return default
    return float(text)


def _float_or_none(value: str) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    return float(text)


def read_universe_rows(path: str | Path) -> list[dict[str, str]]:
    csv_path = Path(path)

    if not csv_path.exists():
        raise FileNotFoundError(f"Universe file not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return [dict(row) for row in reader]


def universe_fieldnames(path: str | Path) -> list[str]:
    csv_path = Path(path)

    if not csv_path.exists():
        raise FileNotFoundError(f"Universe file not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader.fieldnames or [])


def validate_universe_csv(path: str | Path) -> dict[str, Any]:
    fieldnames = universe_fieldnames(path)
    rows = read_universe_rows(path)

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
    extra_columns = [column for column in fieldnames if column not in REQUIRED_COLUMNS]

    row_errors: list[dict[str, Any]] = []
    tickers_seen: set[str] = set()
    duplicate_tickers: set[str] = set()

    numeric_columns = tuple(
        column
        for column in REQUIRED_COLUMNS
        if column not in {"ticker", "sector"}
    )

    for index, row in enumerate(rows, start=2):
        ticker = (row.get("ticker") or "").strip().upper()

        if not ticker:
            row_errors.append(
                {
                    "line": index,
                    "field": "ticker",
                    "error": "missing ticker",
                }
            )
        elif ticker in tickers_seen:
            duplicate_tickers.add(ticker)
        else:
            tickers_seen.add(ticker)

        for column in numeric_columns:
            value = (row.get(column) or "").strip()

            if column in {"entry", "stop", "target"} and not value:
                continue

            if not value:
                row_errors.append(
                    {
                        "line": index,
                        "field": column,
                        "error": "missing numeric value",
                    }
                )
                continue

            try:
                float(value)
            except ValueError:
                row_errors.append(
                    {
                        "line": index,
                        "field": column,
                        "error": f"invalid numeric value: {value}",
                    }
                )

    return {
        "path": str(path),
        "valid": not missing_columns and not row_errors and not duplicate_tickers,
        "rows": len(rows),
        "columns": fieldnames,
        "required_columns": list(REQUIRED_COLUMNS),
        "missing_columns": missing_columns,
        "extra_columns": extra_columns,
        "duplicate_tickers": sorted(duplicate_tickers),
        "row_errors": row_errors,
    }


def load_universe_csv(path: str | Path) -> list[AssetSnapshot]:
    validation = validate_universe_csv(path)

    if validation["missing_columns"]:
        raise ValueError(f"Universe CSV missing columns: {validation['missing_columns']}")

    if validation["duplicate_tickers"]:
        raise ValueError(f"Universe CSV duplicate tickers: {validation['duplicate_tickers']}")

    if validation["row_errors"]:
        raise ValueError(f"Universe CSV row errors: {validation['row_errors']}")

    rows = read_universe_rows(path)
    assets: list[AssetSnapshot] = []

    for row in rows:
        assets.append(
            AssetSnapshot(
                ticker=row["ticker"].strip().upper(),
                sector=row["sector"].strip() or "UNKNOWN",
                last_close=_float(row["last_close"]),
                avg_volume_brl=_float(row["avg_volume_brl"]),
                trend_score=_float(row["trend_score"]),
                momentum_score=_float(row["momentum_score"]),
                volatility_pct=_float(row["volatility_pct"]),
                atr_pct=_float(row["atr_pct"]),
                liquidity_score=_float(row["liquidity_score"]),
                quality_score=_float(row["quality_score"]),
                news_score=_float(row["news_score"]),
                entry=_float_or_none(row["entry"]),
                stop=_float_or_none(row["stop"]),
                target=_float_or_none(row["target"]),
            )
        )

    return assets


def summarize_universe_csv(path: str | Path) -> dict[str, Any]:
    assets = load_universe_csv(path)
    sectors = Counter(asset.sector for asset in assets)

    avg_volume = (
        sum(asset.avg_volume_brl for asset in assets) / len(assets)
        if assets
        else 0.0
    )
    avg_trend = (
        sum(asset.trend_score for asset in assets) / len(assets)
        if assets
        else 0.0
    )
    avg_momentum = (
        sum(asset.momentum_score for asset in assets) / len(assets)
        if assets
        else 0.0
    )
    avg_volatility = (
        sum(asset.volatility_pct for asset in assets) / len(assets)
        if assets
        else 0.0
    )

    return {
        "path": str(path),
        "assets": len(assets),
        "sectors": dict(sorted(sectors.items())),
        "avg_volume_brl": round(avg_volume, 2),
        "avg_trend_score": round(avg_trend, 2),
        "avg_momentum_score": round(avg_momentum, 2),
        "avg_volatility_pct": round(avg_volatility, 2),
        "top_volume": [
            {
                "ticker": asset.ticker,
                "sector": asset.sector,
                "avg_volume_brl": asset.avg_volume_brl,
            }
            for asset in sorted(
                assets,
                key=lambda item: item.avg_volume_brl,
                reverse=True,
            )[:5]
        ],
    }


def write_universe_template(path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        writer.writerows(TEMPLATE_ROWS)
