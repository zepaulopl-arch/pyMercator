from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

from pymercator import presets as presets_mod
from pymercator.terminal_ui import kv, line, render_table, render_warning_list, short_path

BASKET_CSV_COLUMNS = [
    "ticker",
    "sector",
    "rank",
    "score",
    "entry",
    "initial_stop",
    "target_1",
    "target_2",
    "stop_after_t1",
    "trailing_rule",
    "weight",
    "position_value",
    "risk_per_share",
    "max_loss",
    "quantity",
    "status",
    "warnings",
]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def _read_csv(path: str | Path) -> list[dict[str, Any]]:
    path_obj = Path(path)
    if not path_obj.exists():
        return []

    with path_obj.open("r", encoding="utf-8-sig", newline="") as file:
        return [row for row in csv.DictReader(file)]


def _load_universe(universe_path: str | Path) -> dict[str, str]:
    universe_rows = _read_csv(universe_path)
    universe: dict[str, str] = {}

    for row in universe_rows:
        ticker = str(row.get("ticker", "")).strip().upper()
        sector = str(row.get("sector", "")).strip()
        if ticker and sector:
            universe[ticker] = sector

    return universe


def _read_price_rows(path: str | Path) -> list[dict[str, Any]]:
    file_path = Path(path)
    if not file_path.exists():
        return []

    rows: list[dict[str, Any]] = []
    with file_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            date_value = str(row.get("date", "")).strip()
            close = _safe_float(row.get("close"), 0.0)
            if date_value and close > 0:
                rows.append({
                    "date": date_value,
                    "close": close,
                    "high": _safe_float(row.get("high"), 0.0),
                    "low": _safe_float(row.get("low"), 0.0),
                })

    rows.sort(key=lambda item: item["date"])
    return rows


def _price_file_for_ticker(prices_dir: str | Path, ticker: str) -> Path:
    root = Path(prices_dir)
    ticker_text = ticker.upper().strip()
    ticker_base = ticker_text.replace(".SA", "")

    candidates = [
        root / f"{ticker_text}.csv",
        root / f"{ticker_base}.SA.csv",
        root / f"{ticker_base}.csv",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0]


def _compute_atr_pct(row: dict[str, Any], prices_dir: str | Path) -> float:
    atr_pct = _safe_float(row.get("atr_pct"), 0.0)
    if atr_pct > 0:
        return atr_pct

    ticker = str(row.get("ticker", "")).strip()
    price_path = _price_file_for_ticker(prices_dir, ticker)
    price_rows = _read_price_rows(price_path)
    if len(price_rows) < 2:
        return 0.0

    true_ranges: list[float] = []
    previous_close = price_rows[0]["close"]
    for item in price_rows[1:]:
        high = item.get("high", 0.0)
        low = item.get("low", 0.0)
        close = item.get("close", 0.0)
        tr = max(high - low, abs(high - previous_close), abs(low - previous_close))
        true_ranges.append(tr)
        previous_close = close

    if not true_ranges:
        return 0.0

    recent = true_ranges[-14:]
    avg_tr = sum(recent) / len(recent)
    entry = _safe_float(row.get("return_5d"), 0.0)
    entry = _safe_float(row.get("close"), 0.0) or avg_tr
    return round((avg_tr / max(entry, 1.0)) * 100.0, 4)


def _normalize(values: list[float]) -> list[float]:
    if not values:
        return []

    valid = [v for v in values if math.isfinite(v)]
    if not valid:
        return [0.0 for _ in values]

    minimum = min(valid)
    maximum = max(valid)
    if maximum == minimum:
        return [0.5 for _ in values]

    return [max(0.0, min(1.0, (value - minimum) / (maximum - minimum))) for value in values]


def _load_feature_matrix(matrix_path: str | Path) -> list[dict[str, Any]]:
    rows = _read_csv(matrix_path)
    result: list[dict[str, Any]] = []

    for row in rows:
        ticker = str(row.get("ticker", "")).strip().upper()
        sector = str(row.get("sector", "")).strip()
        if not ticker or not sector:
            continue

        result.append({
            "ticker": ticker,
            "sector": sector,
            "momentum_score": _safe_float(row.get("momentum_score"), 0.0),
            "trend_score": _safe_float(row.get("trend_score"), 0.0),
            "news_score": _safe_float(row.get("news_score"), 0.0),
            "return_5d": _safe_float(row.get("return_5d"), 0.0),
            "volatility_20d": _safe_float(row.get("volatility_20d"), 0.0),
            "atr_pct": _safe_float(row.get("atr_pct"), 0.0),
        })

    return result


def _load_prediction_evaluation(evaluation_path: str | Path) -> dict[str, Any]:
    path_obj = Path(evaluation_path)
    if not path_obj.exists():
        return {}

    try:
        return json.loads(path_obj.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _build_scores(rows: list[dict[str, Any]], evaluation: dict[str, Any]) -> list[dict[str, Any]]:
    momentum = [row["momentum_score"] for row in rows]
    trend = [row["trend_score"] for row in rows]
    news = [row["news_score"] for row in rows]
    returns = [row["return_5d"] for row in rows]
    volatility = [row["volatility_20d"] for row in rows]

    momentum_norm = _normalize(momentum)
    trend_norm = _normalize(trend)
    news_norm = _normalize(news)
    return_norm = _normalize(returns)
    volatility_norm = _normalize(volatility)

    sensitivity = 1.0
    if evaluation:
        summary = evaluation.get("summary", {})
        best_accuracy = _safe_float(summary.get("best_accuracy"), 0.0)
        sensitivity += min(0.05, best_accuracy * 0.1)

    scored_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        score = (
            0.30 * momentum_norm[index]
            + 0.25 * trend_norm[index]
            + 0.20 * news_norm[index]
            + 0.15 * return_norm[index]
            - 0.10 * volatility_norm[index]
        )
        score = max(0.0, min(1.0, score)) * sensitivity
        scored_row = row.copy()
        scored_row["score"] = round(score, 6)
        scored_rows.append(scored_row)

    scored_rows.sort(key=lambda item: item["score"], reverse=True)
    return scored_rows


def _select_basket_candidates(
    rows: list[dict[str, Any]],
    slots: int,
    min_sectors: int,
    max_sector_positions: int = 2,
) -> list[dict[str, Any]]:
    if len(rows) < slots:
        return []

    sectors = sorted({row["sector"] for row in rows})
    if len(sectors) < min_sectors:
        return []

    selected: list[dict[str, Any]] = []
    sector_count: dict[str, int] = {}

    # ensure at least min_sectors are represented
    top_by_sector: list[dict[str, Any]] = []
    for sector in sectors:
        candidate = next((row for row in rows if row["sector"] == sector), None)
        if candidate:
            top_by_sector.append(candidate)

    top_by_sector.sort(key=lambda row: row["score"], reverse=True)
    for row in top_by_sector[:min_sectors]:
        selected.append(row)
        sector_count[row["sector"]] = sector_count.get(row["sector"], 0) + 1

    for row in rows:
        if len(selected) >= slots:
            break
        if row in selected:
            continue
        count = sector_count.get(row["sector"], 0)
        if count >= max_sector_positions:
            continue
        selected.append(row)
        sector_count[row["sector"]] = count + 1

    if len(selected) < slots or len({row["sector"] for row in selected}) < min_sectors:
        return []

    return selected[:slots]


def _build_row(
    row: dict[str, Any],
    rank: int,
    weight: float,
    capital: float,
    risk_per_trade: float,
    lot_size: int,
    prices_dir: str | Path,
) -> dict[str, Any]:
    ticker = row["ticker"]
    sector = row["sector"]
    entry = 0.0
    warnings: list[str] = []

    price_path = _price_file_for_ticker(prices_dir, ticker)
    price_rows = _read_price_rows(price_path)
    if price_rows:
        entry = price_rows[-1]["close"]

    atr_pct = _compute_atr_pct(row, prices_dir)
    atr = entry * atr_pct / 100.0
    initial_stop = max(0.0, entry - atr)
    risk_per_share = max(0.0, entry - initial_stop)
    target_1 = entry + risk_per_share
    target_2 = entry + 2 * risk_per_share
    stop_after_t1 = entry
    trailing_rule = "after_target_2: max(entry, close - ATR)"

    position_value = capital * weight
    max_loss_per_trade = capital * risk_per_trade
    quantity_by_risk = math.floor(max_loss_per_trade / max(risk_per_share, 1e-9)) if risk_per_share > 0 else 0.0
    quantity_by_weight = math.floor(position_value / max(entry, 1e-9)) if entry > 0 else 0.0
    quantity = int(min(quantity_by_risk, quantity_by_weight))
    if lot_size > 1:
        quantity = (quantity // lot_size) * lot_size

    if entry <= 0 or risk_per_share <= 0 or quantity <= 0:
        warnings.append("Quantity cannot be sized for lot rules or invalid price")

    max_loss = float(quantity) * risk_per_share
    status = "OK" if quantity > 0 and not warnings else "INVALID"

    return {
        "ticker": ticker,
        "sector": sector,
        "rank": rank,
        "score": round(row["score"], 6),
        "entry": round(entry, 4),
        "initial_stop": round(initial_stop, 4),
        "target_1": round(target_1, 4),
        "target_2": round(target_2, 4),
        "stop_after_t1": round(stop_after_t1, 4),
        "trailing_rule": trailing_rule,
        "weight": round(weight, 4),
        "position_value": round(position_value, 2),
        "risk_per_share": round(risk_per_share, 4),
        "max_loss": round(max_loss, 2),
        "quantity": quantity,
        "status": status,
        "warnings": "; ".join(warnings),
    }


def _write_csv(output_csv: str | Path, rows: list[dict[str, Any]]) -> None:
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=BASKET_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(output_json: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_txt(output_txt: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(output_txt)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = ["PYMERCATOR DAILY BASKET", line(100)]
    lines.append(kv("CAPITAL", f"{payload['capital']:.2f}"))
    lines.append(kv("SLOTS", payload["slots"]))
    lines.append(kv("MIN SECTORS", payload["min_sectors"]))
    lines.append(kv("MIN WEIGHT", payload["min_weight"]))
    lines.append(kv("RISK PER TRADE", payload["risk_per_trade"]))
    lines.append(kv("STOP MODE", payload["stop_mode"]))
    lines.append(kv("TARGETS", payload["targets"]))
    lines.append("")
    lines.append(render_table(payload["rows"], ["ticker", "sector", "rank", "score", "entry", "initial_stop", "target_1", "target_2", "quantity", "status"], widths={"ticker": 10, "sector": 12, "rank": 4, "score": 7, "entry": 8, "initial_stop": 10, "target_1": 8, "target_2": 8, "quantity": 8, "status": 10}))
    if payload.get("warnings"):
        lines.append("")
        lines.append(render_warning_list(payload["warnings"]))
    output_path.write_text("\n".join(lines), encoding="utf-8")


def render_basket_summary(payload: dict[str, Any]) -> str:
    lines: list[str] = ["PYMERCATOR DAILY BASKET", line(100)]
    lines.append(kv("CAPITAL", f"{payload['capital']:.2f}"))
    lines.append(kv("SLOTS", payload["slots"]))
    lines.append(kv("MIN SECTORS", payload["min_sectors"]))
    lines.append(kv("MIN WEIGHT", payload["min_weight"]))
    lines.append(kv("RISK PER TRADE", payload["risk_per_trade"]))
    lines.append(kv("STOP MODE", payload["stop_mode"]))
    lines.append(kv("TARGETS", payload["targets"]))
    lines.append("")
    lines.append(render_table(payload["rows"], ["ticker", "sector", "rank", "score", "entry", "initial_stop", "target_1", "target_2", "quantity", "status"], widths={"ticker": 10, "sector": 12, "rank": 4, "score": 7, "entry": 8, "initial_stop": 10, "target_1": 8, "target_2": 8, "quantity": 8, "status": 10}))
    if payload.get("warnings"):
        lines.append("")
        lines.append(render_warning_list(payload["warnings"]))
    return "\n".join(lines)


def run_daily_basket(
    *,
    slots: int = 5,
    min_sectors: int = 3,
    min_weight: float = 0.10,
    capital: float = 100000.0,
    risk_per_trade: float = 0.005,
    targets: int = 2,
    stop_mode: str = "progressive",
    prices_dir: str = "data/prices",
    universe: str = "data/universes/ibov_live.csv",
    matrix: str = "storage/features/latest_feature_matrix.csv",
    evaluation: str = "storage/prediction/latest_evaluation.json",
    output_csv: str = "storage/baskets/latest_daily_basket.csv",
    lot_size: int = 100,
) -> dict[str, Any]:
    universe_map = _load_universe(universe)
    rows = _load_feature_matrix(matrix)
    evaluation_payload = _load_prediction_evaluation(evaluation)

    filtered: list[dict[str, Any]] = []
    for row in rows:
        ticker = row["ticker"].upper()
        if ticker not in universe_map:
            continue
        row["sector"] = universe_map.get(ticker, row["sector"])

        price_path = _price_file_for_ticker(prices_dir, ticker)
        price_rows = _read_price_rows(price_path)
        if len(price_rows) < 14:
            continue

        entry = price_rows[-1]["close"]
        if entry <= 0:
            continue

        position_value = capital * max(min_weight, 1.0 / slots)
        if entry <= 0 or position_value / entry < lot_size:
            continue

        row["entry"] = entry
        filtered.append(row)

    scored_rows = _build_scores(filtered, evaluation_payload)
    basket_rows = _select_basket_candidates(scored_rows, slots, min_sectors)

    effective_weight = max(min_weight, 1.0 / slots)
    rows_payload: list[dict[str, Any]] = []
    warnings: list[str] = []

    for rank, row in enumerate(basket_rows, start=1):
        built = _build_row(
            row=row,
            rank=rank,
            weight=effective_weight,
            capital=capital,
            risk_per_trade=risk_per_trade,
            lot_size=lot_size,
            prices_dir=prices_dir,
        )
        rows_payload.append(built)
        if built["warnings"]:
            warnings.append(f"{built['ticker']}: {built['warnings']}")

    output_json = str(Path(output_csv).with_suffix(".json"))
    output_txt = str(Path(output_csv).with_suffix(".txt"))
    payload = {
        "status": "OK" if len(rows_payload) == slots else "FAILED",
        "slots": slots,
        "min_sectors": min_sectors,
        "min_weight": min_weight,
        "capital": capital,
        "risk_per_trade": risk_per_trade,
        "targets": targets,
        "stop_mode": stop_mode,
        "execution_mode": "ANALYSIS_ONLY",
        "output_csv": str(Path(output_csv)),
        "output_json": output_json,
        "output_txt": output_txt,
        "rows": rows_payload,
        "warnings": warnings,
        "evaluation": bool(evaluation_payload),
    }

    _write_csv(output_csv, rows_payload)
    _write_json(output_json, payload)
    _write_txt(output_txt, payload)

    return payload


def load_basket_json(path: str | Path = "storage/baskets/latest_daily_basket.json") -> dict[str, Any]:
    path_obj = Path(path)
    if not path_obj.exists():
        return {"status": "MISSING", "warnings": [f"Basket artifact not found: {path_obj}"]}

    try:
        return json.loads(path_obj.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "INVALID", "warnings": [f"Unable to parse basket artifact: {path_obj}"]}


def resolve_basket_paths(output_csv: str | Path = "storage/baskets/latest_daily_basket.csv") -> tuple[str, str, str]:
    base = Path(output_csv)
    return (
        str(base),
        str(base.with_suffix(".json")),
        str(base.with_suffix(".txt")),
    )
