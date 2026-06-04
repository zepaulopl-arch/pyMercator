from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from pymercator.features_catalog import validate_features_catalog
from pymercator.manifest import load_json


def _read_universe(path: str | Path) -> list[dict[str, Any]]:
    file_path = Path(path)

    with file_path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def _price_file_for_ticker(prices_dir: str | Path, ticker: str) -> Path:
    root = Path(prices_dir)
    ticker_text = ticker.upper().strip()

    candidates = [
        root / f"{ticker_text}.csv",
        root / f"{ticker_text}.SA.csv",
        root / f"{ticker_text.replace('.SA', '')}.SA.csv",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[-1]


def _read_closes(path: Path) -> list[float]:
    if not path.exists():
        return []

    rows: list[tuple[str, float]] = []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            date_value = str(row.get("date", "")).strip()
            close = _to_float(row.get("close"), 0.0)

            if date_value and close > 0:
                rows.append((date_value, close))

    rows.sort(key=lambda item: item[0])
    return [close for _, close in rows]


def _return_pct(closes: list[float], window: int) -> float:
    if len(closes) <= window:
        return 0.0

    last = closes[-1]
    previous = closes[-window - 1]

    if previous <= 0:
        return 0.0

    return round(((last / previous) - 1.0) * 100.0, 4)


def _enabled_feature_names(features_file: str | Path) -> list[str]:
    payload = validate_features_catalog(features_file)

    if not payload["valid"]:
        return []

    return [
        item["name"]
        for item in payload.get("items", [])
        if item.get("enabled", True)
    ]


def build_feature_matrix(
    *,
    universe: str | Path,
    prices_dir: str | Path = "data/prices",
    context: str | Path = "config/market_context_auto.json",
    features: str | Path = "config/features_catalog.json",
) -> dict[str, Any]:
    universe_rows = _read_universe(universe)
    context_payload = load_json(context, {})
    feature_names = _enabled_feature_names(features)

    matrix_rows: list[dict[str, Any]] = []
    missing_price_files: list[str] = []
    matrix_tickers: set[str] = set()

    for asset in universe_rows:
        ticker = str(asset.get("ticker", "")).strip()
        sector = str(asset.get("sector", "")).strip()

        if ticker:
            matrix_tickers.add(ticker.upper())

        price_file = _price_file_for_ticker(prices_dir, ticker)
        closes = _read_closes(price_file)

        if not closes:
            missing_price_files.append(ticker)

        row: dict[str, Any] = {
            "ticker": ticker,
            "sector": sector,
        }

        for feature in feature_names:
            if feature == "return_1d":
                row[feature] = _return_pct(closes, 1)
            elif feature == "return_5d":
                row[feature] = _return_pct(closes, 5)
            elif feature == "return_20d":
                row[feature] = _return_pct(closes, 20)
            elif feature == "volatility_20d":
                row[feature] = round(_to_float(asset.get("volatility_pct")), 4)
            elif feature == "atr_pct":
                row[feature] = round(_to_float(asset.get("atr_pct")), 4)
            elif feature == "trend_score":
                row[feature] = round(_to_float(asset.get("trend_score")), 4)
            elif feature == "momentum_score":
                row[feature] = round(_to_float(asset.get("momentum_score")), 4)
            elif feature == "news_score":
                row[feature] = round(_to_float(asset.get("news_score"), 50.0), 4)
            elif feature == "market_trend":
                row[feature] = context_payload.get("market_trend", "")
            elif feature == "market_volatility":
                row[feature] = context_payload.get("market_volatility", "")
            else:
                row[feature] = ""

        matrix_rows.append(row)

    return {
        "universe": str(universe),
        "prices_dir": str(prices_dir),
        "context": str(context),
        "features": str(features),
        "rows": len(matrix_rows),
        "assets": len(matrix_tickers),
        "universe_assets": len(
            {str(row.get("ticker", "")).strip().upper() for row in universe_rows}
            - {""}
        ),
        "columns": ["ticker", "sector", *feature_names],
        "missing_price_files": sorted(set(missing_price_files)),
        "missing_price_files_count": len(set(missing_price_files)),
        "matrix": matrix_rows,
    }


def write_feature_matrix(
    *,
    universe: str | Path,
    prices_dir: str | Path,
    context: str | Path,
    features: str | Path,
    output: str | Path,
) -> dict[str, Any]:
    payload = build_feature_matrix(
        universe=universe,
        prices_dir=prices_dir,
        context=context,
        features=features,
    )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=payload["columns"])
        writer.writeheader()
        writer.writerows(payload["matrix"])

    payload["output"] = str(output_path)

    return payload


def render_feature_matrix_summary(payload: dict[str, Any]) -> str:
    line = "-" * 100

    lines = [
        "PYMERCATOR FEATURE MATRIX",
        line,
        f"{'UNIVERSE':<22} {payload['universe']}",
        f"{'PRICES DIR':<22} {payload['prices_dir']}",
        f"{'CONTEXT':<22} {payload['context']}",
        f"{'FEATURES':<22} {payload['features']}",
        f"{'OUTPUT':<22} {payload.get('output', '-')}",
        f"{'ROWS':<22} {payload['rows']}",
        f"{'ASSETS':<22} {payload.get('assets', payload['rows'])}",
        f"{'COLUMNS':<22} {len(payload['columns'])}",
        f"{'MISSING PRICES':<22} {payload['missing_price_files_count']}",
        "",
        "COLUMNS",
        line,
        ", ".join(payload["columns"]),
    ]

    if payload["missing_price_files"]:
        lines.extend(["", "MISSING PRICE FILES", line])
        lines.append(", ".join(payload["missing_price_files"][:40]))

    return "\n".join(lines)
