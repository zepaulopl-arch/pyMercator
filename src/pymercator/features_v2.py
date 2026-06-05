from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

DEFAULT_FEATURES_CONFIG: dict[str, Any] = {
    "schema_version": "features_config.v2",
    "enabled": True,
    "feature_set": "core_v2",
    "enabled_groups": {
        "returns": True,
        "trend": True,
        "momentum": True,
        "volatility": True,
        "volume_liquidity": True,
        "relative_strength": True,
        "sector_breadth": True,
        "risk_drawdown": True,
        "compression": True,
        "market_context": True,
        "candle": False,
        "statistical_lite": False,
        "tsfresh": False,
    },
    "selection": {
        "enabled": True,
        "max_missing_pct": 0.25,
        "drop_constant": True,
        "corr_threshold": 0.95,
        "mutual_information_top_n": 120,
        "per_horizon_selection": True,
    },
    "history": {
        "max_rows_per_asset": 360,
    },
}

METADATA_COLUMNS = {
    "date",
    "ticker",
    "sector",
    "_close",
    "close",
    "open",
    "high",
    "low",
    "volume",
    "feature_set",
}

COMPATIBILITY_COLUMNS = [
    "return_1d",
    "return_5d",
    "return_20d",
    "volatility_20d",
    "atr_pct",
    "trend_score",
    "momentum_score",
    "news_score",
    "market_trend",
    "market_volatility",
]
PINNED_FEATURE_COLUMNS = [
    "ret_1d",
    "ret_5d",
    "ret_20d",
    "ret_60d",
    "log_ret_1d",
    "ma_stack_score",
    "rsi_14",
    "atr_14_pct",
    "realized_vol_20",
    "volume_zscore_20",
    "rel_ret_vs_ibov_20d",
    "drawdown_60",
    "bollinger_width",
    "context_score",
    *COMPATIBILITY_COLUMNS,
]

DEFAULT_HISTORY_OUTPUT = "storage/features/latest_feature_history.csv"
DEFAULT_MATRIX_OUTPUT = "storage/features/latest_feature_matrix.csv"
DEFAULT_AUDIT_OUTPUT = "storage/features/latest_feature_audit.json"
DEFAULT_LIST_OUTPUT = "storage/features/latest_feature_list.json"


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _round(value: Any, digits: int = 6) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return round(number, digits)


def load_features_config(path: str | Path = "config/features.json") -> dict[str, Any]:
    config = json.loads(json.dumps(DEFAULT_FEATURES_CONFIG))
    source = Path(path)
    if source.exists():
        try:
            loaded = json.loads(source.read_text(encoding="utf-8-sig"))
        except Exception:
            loaded = {}
        if isinstance(loaded, dict):
            config.update({key: value for key, value in loaded.items() if key not in {"enabled_groups", "selection"}})
            if isinstance(loaded.get("enabled_groups"), dict):
                config["enabled_groups"].update(loaded["enabled_groups"])
            if isinstance(loaded.get("selection"), dict):
                config["selection"].update(loaded["selection"])
            if isinstance(loaded.get("history"), dict):
                config["history"].update(loaded["history"])
    return config


def _read_csv(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _write_csv(path: str | Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
    return candidates[1]


def _read_price_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _read_csv(path):
        date_text = str(row.get("date", "")).strip()
        close = _to_float(row.get("close"))
        if not date_text or close <= 0:
            continue
        rows.append(
            {
                "date": date_text,
                "open": _to_float(row.get("open"), close),
                "high": _to_float(row.get("high"), close),
                "low": _to_float(row.get("low"), close),
                "close": close,
                "volume": _to_float(row.get("volume"), 0.0),
            }
        )
    rows.sort(key=lambda item: str(item["date"]))
    return rows


def _pct_change(values: list[float], index: int, window: int) -> float | None:
    if index - window < 0:
        return None
    previous = values[index - window]
    current = values[index]
    if previous <= 0:
        return None
    return ((current / previous) - 1.0) * 100.0


def _rolling(values: list[float], index: int, window: int) -> list[float]:
    start = max(0, index - window + 1)
    return values[start : index + 1]


def _mean(values: list[float]) -> float | None:
    clean = [value for value in values if math.isfinite(value)]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _std(values: list[float]) -> float | None:
    clean = [value for value in values if math.isfinite(value)]
    if len(clean) < 2:
        return None
    mean = sum(clean) / len(clean)
    variance = sum((value - mean) ** 2 for value in clean) / len(clean)
    return math.sqrt(variance)


def _zscore(values: list[float], index: int, window: int) -> float | None:
    current = values[index]
    sample = _rolling(values, index, window)
    mean = _mean(sample)
    std = _std(sample)
    if mean is None or not std:
        return None
    return (current - mean) / std


def _ema(values: list[float], window: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (window + 1.0)
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1.0 - alpha) * result[-1])
    return result


def _slope(values: list[float], index: int, window: int) -> float | None:
    if index - window < 0:
        return None
    previous = values[index - window]
    current = values[index]
    if previous == 0:
        return None
    return ((current / previous) - 1.0) * 100.0


def _rsi(closes: list[float], window: int) -> list[float | None]:
    result: list[float | None] = [None for _ in closes]
    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, len(closes)):
        delta = closes[index] - closes[index - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
        if index >= window:
            avg_gain = sum(gains[index - window : index]) / window
            avg_loss = sum(losses[index - window : index]) / window
            if avg_loss == 0:
                result[index] = 100.0
            else:
                rs = avg_gain / avg_loss
                result[index] = 100.0 - (100.0 / (1.0 + rs))
    return result


def _true_ranges(highs: list[float], lows: list[float], closes: list[float]) -> list[float]:
    ranges: list[float] = []
    for index, high in enumerate(highs):
        low = lows[index]
        previous_close = closes[index - 1] if index > 0 else closes[index]
        ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    return ranges


def _obv(closes: list[float], volumes: list[float]) -> list[float]:
    result = [0.0 for _ in closes]
    for index in range(1, len(closes)):
        direction = 1.0 if closes[index] > closes[index - 1] else -1.0 if closes[index] < closes[index - 1] else 0.0
        result[index] = result[index - 1] + direction * volumes[index]
    return result


def _corr(left: list[float], right: list[float]) -> float | None:
    pairs = [
        (a, b)
        for a, b in zip(left, right, strict=False)
        if math.isfinite(a) and math.isfinite(b)
    ]
    if len(pairs) < 3:
        return None
    xs = [item[0] for item in pairs]
    ys = [item[1] for item in pairs]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def _beta(asset_returns: list[float], index_returns: list[float]) -> float | None:
    pairs = [
        (a, b)
        for a, b in zip(asset_returns, index_returns, strict=False)
        if math.isfinite(a) and math.isfinite(b)
    ]
    if len(pairs) < 10:
        return None
    xs = [item[1] for item in pairs]
    ys = [item[0] for item in pairs]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    variance = sum((x - mean_x) ** 2 for x in xs)
    if variance == 0:
        return None
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    return covariance / variance


def _load_index_returns(indices_dir: str | Path) -> dict[str, float]:
    candidates = [
        Path(indices_dir) / "^BVSP.csv",
        Path(indices_dir) / "IBOV.csv",
        Path(indices_dir) / "IBOV.SA.csv",
    ]
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        rows = _read_price_rows(candidate)
        if rows:
            break
    closes = [_to_float(row["close"]) for row in rows]
    returns: dict[str, float] = {}
    for index, row in enumerate(rows):
        ret = _pct_change(closes, index, 1)
        returns[str(row["date"])] = ret if ret is not None else 0.0
    return returns


def _market_context_values(context_path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(context_path).read_text(encoding="utf-8-sig"))
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    summary = payload.get("regime_summary", {})
    if not isinstance(summary, dict):
        summary = {}
    sector_context = payload.get("sector_context", {})
    if not isinstance(sector_context, dict):
        sector_context = {}
    return {
        "context_score": _to_float(summary.get("context_score"), 50.0),
        "market_trend": str(summary.get("market_trend") or payload.get("market_trend") or "").upper(),
        "market_volatility": str(summary.get("market_volatility") or payload.get("market_volatility") or "").upper(),
        "risk_off_flag": 1.0 if str(summary.get("market_regime", "")).upper() == "RISK_OFF" else 0.0,
        "risk_on_flag": 1.0 if str(summary.get("market_regime", "")).upper() == "RISK_ON" else 0.0,
        "event_risk_flag": 1.0 if payload.get("events") else 0.0,
        "oil_stress_score": 1.0 if "oil" in [str(item).lower() for item in summary.get("main_risks", []) or []] else 0.0,
        "usdbrl_stress_score": 1.0 if "usdbrl" in [str(item).lower() for item in summary.get("main_risks", []) or []] else 0.0,
        "sector_context": sector_context,
    }


def _sector_context_score(sector_context: dict[str, Any], sector: str) -> float:
    item = sector_context.get(sector) or sector_context.get(str(sector).lower()) or {}
    if not isinstance(item, dict):
        return 0.0
    status = str(item.get("context") or item.get("status") or "").upper()
    return {"FAVORABLE": 1.0, "OK": 0.5, "NEUTRAL": 0.0, "WATCH": -0.25, "BLOCKED": -1.0}.get(status, 0.0)


def _safe_value(value: Any) -> float | str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return _round(value)


def _asset_feature_rows(
    *,
    ticker: str,
    sector: str,
    price_rows: list[dict[str, Any]],
    index_returns: dict[str, float],
    context: dict[str, Any],
    groups: dict[str, bool],
    max_rows: int = 0,
) -> list[dict[str, Any]]:
    closes = [_to_float(row["close"]) for row in price_rows]
    highs = [_to_float(row["high"], closes[index]) for index, row in enumerate(price_rows)]
    lows = [_to_float(row["low"], closes[index]) for index, row in enumerate(price_rows)]
    volumes = [_to_float(row["volume"], 0.0) for row in price_rows]
    ema_9 = _ema(closes, 9)
    ema_21 = _ema(closes, 21)
    ema_50 = _ema(closes, 50)
    ema_200 = _ema(closes, 200)
    rsi_7 = _rsi(closes, 7)
    rsi_14 = _rsi(closes, 14)
    rsi_21 = _rsi(closes, 21)
    ema_12 = _ema(closes, 12)
    ema_26 = _ema(closes, 26)
    macd = [a - b for a, b in zip(ema_12, ema_26, strict=True)]
    macd_signal = _ema(macd, 9)
    macd_hist = [a - b for a, b in zip(macd, macd_signal, strict=True)]
    tr = _true_ranges(highs, lows, closes)
    atr_14 = [(_mean(_rolling(tr, index, 14)) or 0.0) for index in range(len(tr))]
    daily_returns = [(_pct_change(closes, index, 1) or 0.0) for index in range(len(closes))]
    ret_by_window = {
        window: [(_pct_change(closes, cursor, window) or 0.0) for cursor in range(len(closes))]
        for window in (1, 2, 5, 10, 20, 60)
    }
    obv = _obv(closes, volumes)
    typical = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(len(closes))]
    mf_raw = [typical[c] * volumes[c] for c in range(len(closes))]
    pos_flow: list[float] = []
    neg_flow: list[float] = []
    for c in range(len(closes)):
        if c == 0 or closes[c] >= closes[c - 1]:
            pos_flow.append(mf_raw[c])
            neg_flow.append(0.0)
        else:
            pos_flow.append(0.0)
            neg_flow.append(mf_raw[c])
    widths = [
        (((4.0 * (_std(_rolling(closes, cursor, 20)) or 0.0)) / (_mean(_rolling(closes, cursor, 20)) or 1.0)) * 100.0)
        for cursor in range(len(closes))
    ]
    date_returns = [index_returns.get(str(price_rows[c]["date"]), 0.0) for c in range(len(price_rows))]
    market_trend = context.get("market_trend", "")
    market_volatility = context.get("market_volatility", "")

    rows: list[dict[str, Any]] = []
    start_index = max(0, len(price_rows) - max_rows) if max_rows > 0 else 0
    for index in range(start_index, len(price_rows)):
        price_row = price_rows[index]
        close = closes[index]
        high = highs[index]
        low = lows[index]
        volume = volumes[index]
        row: dict[str, Any] = {
            "date": price_row["date"],
            "ticker": ticker,
            "sector": sector,
            "_close": close,
            "feature_set": "core_v2",
        }
        if groups.get("returns", True):
            for window in (1, 2, 5, 10, 20, 60):
                row[f"ret_{window}d"] = _safe_value(_pct_change(closes, index, window))
            ret_1d = _pct_change(closes, index, 1)
            row["log_ret_1d"] = _safe_value(math.log(close / closes[index - 1]) if index > 0 and closes[index - 1] > 0 else None)
            for window in (5, 20, 60):
                row[f"ret_{window}d_zscore"] = _safe_value(_zscore(ret_by_window[window], index, 60))
            row["return_1d"] = _safe_value(ret_1d)
            row["return_5d"] = row["ret_5d"]
            row["return_20d"] = row["ret_20d"]
        if groups.get("trend", True):
            row["ema_9"] = _safe_value(ema_9[index])
            row["ema_21"] = _safe_value(ema_21[index])
            row["ema_50"] = _safe_value(ema_50[index])
            row["ema_200"] = _safe_value(ema_200[index])
            for window, series in ((21, ema_21), (50, ema_50), (200, ema_200)):
                row[f"dist_ema_{window}"] = _safe_value(((close / series[index]) - 1.0) * 100.0 if series[index] else None)
                row[f"ema_{window}_slope"] = _safe_value(_slope(series, index, min(10, window)))
            stack = sum(
                1.0
                for value in (ema_9[index], ema_21[index], ema_50[index], ema_200[index])
                if close >= value
            )
            row["ma_stack_score"] = _safe_value((stack / 4.0) * 100.0)
            row["adx_14"] = _safe_value(_mean([abs(value) for value in _rolling(daily_returns, index, 14)]))
            row["trend_score"] = row["ma_stack_score"]
        if groups.get("momentum", True):
            row["rsi_7"] = _safe_value(rsi_7[index])
            row["rsi_14"] = _safe_value(rsi_14[index])
            row["rsi_21"] = _safe_value(rsi_21[index])
            row["rsi_14_slope"] = _safe_value(_slope([value or 50.0 for value in rsi_14], index, 5))
            row["macd"] = _safe_value(macd[index])
            row["macd_signal"] = _safe_value(macd_signal[index])
            row["macd_hist"] = _safe_value(macd_hist[index])
            row["macd_hist_slope"] = _safe_value(_slope(macd_hist, index, 5))
            row["roc_10"] = _safe_value(_pct_change(closes, index, 10))
            row["roc_20"] = _safe_value(_pct_change(closes, index, 20))
            tp_window = _rolling(typical, index, 20)
            tp_mean = _mean(tp_window)
            mean_dev = _mean([abs(value - (tp_mean or 0.0)) for value in tp_window])
            row["cci_20"] = _safe_value((typical[index] - tp_mean) / (0.015 * mean_dev) if tp_mean is not None and mean_dev else None)
            high_window = max(_rolling(highs, index, 14))
            low_window = min(_rolling(lows, index, 14))
            row["williams_r"] = _safe_value(((high_window - close) / (high_window - low_window)) * -100.0 if high_window != low_window else None)
            row["momentum_score"] = _safe_value(rsi_14[index] or 50.0)
        if groups.get("volatility", True):
            row["atr_14"] = _safe_value(atr_14[index])
            row["atr_14_pct"] = _safe_value((atr_14[index] / close) * 100.0 if close else None)
            row["atr_zscore_60"] = _safe_value(_zscore(atr_14, index, 60))
            for window in (5, 20, 60):
                vol = _std(_rolling(daily_returns, index, window))
                row[f"realized_vol_{window}"] = _safe_value((vol or 0.0) * math.sqrt(252.0))
            rv5 = _to_float(row.get("realized_vol_5"))
            rv20 = _to_float(row.get("realized_vol_20"))
            rv60 = _to_float(row.get("realized_vol_60"))
            row["vol_ratio_5_20"] = _safe_value(rv5 / rv20 if rv20 else None)
            row["vol_ratio_20_60"] = _safe_value(rv20 / rv60 if rv60 else None)
            ma20 = _mean(_rolling(closes, index, 20))
            std20 = _std(_rolling(closes, index, 20))
            row["bollinger_width"] = _safe_value(((4.0 * std20) / ma20) * 100.0 if ma20 and std20 else None)
            row["bollinger_width_zscore"] = _safe_value(_zscore(widths, index, 60))
            row["volatility_regime"] = 1.0 if rv20 > rv60 else 0.0
            row["volatility_20d"] = row["realized_vol_20"]
            row["atr_pct"] = row["atr_14_pct"]
        if groups.get("volume_liquidity", True):
            for window in (20, 60):
                row[f"volume_zscore_{window}"] = _safe_value(_zscore(volumes, index, window))
            vol5 = _mean(_rolling(volumes, index, 5))
            vol20 = _mean(_rolling(volumes, index, 20))
            vol60 = _mean(_rolling(volumes, index, 60))
            row["volume_ratio_5_20"] = _safe_value(vol5 / vol20 if vol20 else None)
            row["volume_ratio_20_60"] = _safe_value(vol20 / vol60 if vol60 else None)
            row["obv"] = _safe_value(obv[index])
            row["obv_slope"] = _safe_value(_slope(obv, index, 10))
            pos14 = sum(_rolling(pos_flow, index, 14))
            neg14 = sum(_rolling(neg_flow, index, 14))
            row["mfi_14"] = _safe_value(100.0 if neg14 == 0 else 100.0 - (100.0 / (1.0 + (pos14 / neg14))))
            dollar_volume = close * volume
            row["dollar_volume_20"] = _safe_value(_mean([closes[c] * volumes[c] for c in range(max(0, index - 19), index + 1)]))
            row["amihud_illiquidity"] = _safe_value(abs(daily_returns[index]) / dollar_volume if dollar_volume else None)
            row["liquidity_score"] = _safe_value(min(100.0, math.log10(max(dollar_volume, 1.0)) * 10.0))
        if groups.get("relative_strength", True):
            for window in (5, 20, 60):
                asset_ret = _pct_change(closes, index, window)
                if index - window >= 0:
                    index_base = date_returns[index - window]
                    index_now = date_returns[index]
                    index_ret = sum(date_returns[index - window + 1 : index + 1])
                else:
                    index_base = 0.0
                    index_now = 0.0
                    index_ret = None
                _ = index_base, index_now
                row[f"rel_ret_vs_ibov_{window}d"] = _safe_value(asset_ret - index_ret if asset_ret is not None and index_ret is not None else None)
            asset_60 = _rolling(daily_returns, index, 60)
            ibov_60 = _rolling(date_returns, index, 60)
            beta = _beta(asset_60, ibov_60)
            row["beta_60"] = _safe_value(beta)
            row["corr_ibov_60"] = _safe_value(_corr(asset_60, ibov_60))
            for window in (20, 60):
                asset_ret = _pct_change(closes, index, window)
                market_ret = sum(_rolling(date_returns, index, window))
                row[f"alpha_{window}"] = _safe_value(asset_ret - market_ret if asset_ret is not None else None)
        if groups.get("risk_drawdown", True):
            for window in (20, 60, 120):
                highs_window = _rolling(closes, index, window)
                high_n = max(highs_window)
                low_n = min(highs_window)
                row[f"drawdown_{window}"] = _safe_value(((close / high_n) - 1.0) * 100.0 if high_n else None)
                row[f"distance_from_{window}d_high"] = _safe_value(((close / high_n) - 1.0) * 100.0 if high_n else None)
                row[f"distance_from_{window}d_low"] = _safe_value(((close / low_n) - 1.0) * 100.0 if low_n else None)
            for window in (20, 60):
                sample = _rolling(closes, index, window)
                row[f"new_high_{window}"] = 1.0 if close >= max(sample) else 0.0
                row[f"new_low_{window}"] = 1.0 if close <= min(sample) else 0.0
        if groups.get("compression", True):
            high20 = max(_rolling(highs, index, 20))
            low20 = min(_rolling(lows, index, 20))
            row["range_compression_20"] = _safe_value(((high20 - low20) / close) * 100.0 if close else None)
            width = _to_float(row.get("bollinger_width"), 0.0)
            width_z = _to_float(row.get("bollinger_width_zscore"), 0.0)
            row["bollinger_squeeze"] = 1.0 if width_z < -1.0 else 0.0
            row["breakout_20"] = 1.0 if close >= high20 else 0.0
            row["breakdown_20"] = 1.0 if close <= low20 else 0.0
            range7 = max(_rolling(highs, index, 7)) - min(_rolling(lows, index, 7))
            range20 = high20 - low20
            row["narrow_range_7"] = 1.0 if range20 and range7 / range20 < 0.35 else 0.0
            row["atr_compression"] = 1.0 if _to_float(row.get("atr_zscore_60")) < -1.0 else 0.0
            _ = width
        if groups.get("market_context", True):
            row["context_score"] = _safe_value(context.get("context_score", 50.0))
            row["risk_off_flag"] = _safe_value(context.get("risk_off_flag", 0.0))
            row["risk_on_flag"] = _safe_value(context.get("risk_on_flag", 0.0))
            row["event_risk_flag"] = _safe_value(context.get("event_risk_flag", 0.0))
            row["oil_stress_score"] = _safe_value(context.get("oil_stress_score", 0.0))
            row["usdbrl_stress_score"] = _safe_value(context.get("usdbrl_stress_score", 0.0))
            row["sector_context_score"] = _safe_value(_sector_context_score(context.get("sector_context", {}), sector))
            row["market_trend"] = market_trend
            row["market_volatility"] = market_volatility
            row["news_score"] = 50.0
        rows.append(row)
    return rows


def _add_sector_features(rows: list[dict[str, Any]], groups: dict[str, bool]) -> None:
    if not rows or not (groups.get("sector_breadth", True) or groups.get("relative_strength", True)):
        return
    by_date_sector: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_date_sector[(str(row["date"]), str(row["sector"]))].append(row)
    sector_date_scores: dict[tuple[str, str], dict[str, float]] = {}
    for key, items in by_date_sector.items():
        sector_ret_5 = _mean([_to_float(item.get("ret_5d")) for item in items]) or 0.0
        sector_ret_20 = _mean([_to_float(item.get("ret_20d")) for item in items]) or 0.0
        sector_ret_60 = _mean([_to_float(item.get("ret_60d")) for item in items]) or 0.0
        sector_trend = _mean([_to_float(item.get("trend_score")) for item in items]) or 0.0
        sector_mom = _mean([_to_float(item.get("momentum_score")) for item in items]) or 0.0
        sector_vol = _mean([_to_float(item.get("volatility_20d")) for item in items]) or 0.0
        breadth_ema = sum(1 for item in items if _to_float(item.get("dist_ema_21")) > 0) / len(items)
        breadth_mom = sum(1 for item in items if _to_float(item.get("momentum_score")) >= 50) / len(items)
        sector_date_scores[key] = {
            "sector_ret_5d": sector_ret_5,
            "sector_ret_20d": sector_ret_20,
            "sector_ret_60d": sector_ret_60,
            "sector_trend_score": sector_trend,
            "sector_momentum_score": sector_mom,
            "sector_vol_score": sector_vol,
            "sector_breadth_ema21": breadth_ema * 100.0,
            "sector_breadth_mom": breadth_mom * 100.0,
        }
    ranks_by_date: dict[str, dict[str, int]] = defaultdict(dict)
    grouped_by_date: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for (date_text, sector), values in sector_date_scores.items():
        grouped_by_date[date_text].append((sector, values["sector_ret_20d"]))
    for date_text, items in grouped_by_date.items():
        for rank, (sector, _score) in enumerate(sorted(items, key=lambda item: -item[1]), start=1):
            ranks_by_date[date_text][sector] = rank
    for row in rows:
        key = (str(row["date"]), str(row["sector"]))
        values = sector_date_scores.get(key, {})
        if groups.get("sector_breadth", True):
            for name, value in values.items():
                row[name] = _safe_value(value)
            row["sector_rank"] = ranks_by_date.get(str(row["date"]), {}).get(str(row["sector"]), 0)
        if groups.get("relative_strength", True):
            for window in (5, 20, 60):
                row[f"rel_ret_vs_sector_{window}d"] = _safe_value(
                    _to_float(row.get(f"ret_{window}d")) - _to_float(values.get(f"sector_ret_{window}d"))
                )
            peers = by_date_sector.get(key, [])
            ranked = sorted(_to_float(peer.get("ret_20d")) for peer in peers)
            if ranked:
                value = _to_float(row.get("ret_20d"))
                below = sum(1 for peer_value in ranked if peer_value <= value)
                row["asset_percentile_in_sector"] = _safe_value((below / len(ranked)) * 100.0)


def _candidate_feature_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key, value in row.items():
            if key in METADATA_COLUMNS or key.startswith("target_"):
                continue
            if key not in columns and not isinstance(value, str):
                columns.append(key)
    return columns


def _sample_rows(rows: list[dict[str, Any]], limit: int = 5000) -> list[dict[str, Any]]:
    if len(rows) <= limit:
        return rows
    step = max(1, len(rows) // limit)
    sampled = rows[::step][:limit]
    return sampled or rows[:limit]


def _missing_ratio(rows: list[dict[str, Any]], column: str) -> float:
    missing = 0
    for row in rows:
        value = row.get(column, "")
        if value == "" or value is None:
            missing += 1
    return missing / len(rows) if rows else 1.0


def _constant(rows: list[dict[str, Any]], column: str) -> bool:
    values = {_round(row.get(column), 10) for row in rows if row.get(column, "") not in {"", None}}
    return len(values) <= 1


def _correlation_prune(rows: list[dict[str, Any]], columns: list[str], threshold: float) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    dropped: list[str] = []
    vectors = {
        column: [_to_float(row.get(column), 0.0) for row in rows]
        for column in columns
    }
    for column in columns:
        vector = vectors[column]
        too_close = False
        for kept_column in kept:
            corr = _corr(vector, vectors[kept_column])
            if corr is not None and abs(corr) >= threshold:
                too_close = True
                break
        if too_close:
            dropped.append(column)
        else:
            kept.append(column)
    return kept, dropped


def _target_for_row(rows_by_ticker: dict[str, list[dict[str, Any]]], row: dict[str, Any], horizon: int) -> int | None:
    ticker_rows = rows_by_ticker.get(str(row.get("ticker", "")), [])
    dates = [str(item.get("date")) for item in ticker_rows]
    try:
        index = dates.index(str(row.get("date")))
    except ValueError:
        return None
    if index + horizon >= len(ticker_rows):
        return None
    close = _to_float(ticker_rows[index].get("_close"))
    future = _to_float(ticker_rows[index + horizon].get("_close"))
    if close <= 0:
        return None
    return 1 if future > close else 0


def _mutual_information_scores(
    rows: list[dict[str, Any]],
    columns: list[str],
    horizons: tuple[int, ...] = (5, 20, 60),
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    warnings: list[str] = []
    rows_by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        rows_by_ticker[str(row.get("ticker", ""))].append(row)
    for ticker_rows in rows_by_ticker.values():
        ticker_rows.sort(key=lambda item: str(item.get("date", "")))
    try:
        from sklearn.feature_selection import mutual_info_classif
    except Exception:
        warnings.append("mutual_info_classif unavailable; feature selection kept correlation-pruned columns")
        return {}, warnings
    result: dict[str, list[dict[str, Any]]] = {}
    for horizon in horizons:
        x_values: list[list[float]] = []
        y_values: list[int] = []
        for ticker_rows in rows_by_ticker.values():
            for index, row in enumerate(ticker_rows):
                if index + horizon >= len(ticker_rows):
                    continue
                close = _to_float(row.get("_close"))
                future = _to_float(ticker_rows[index + horizon].get("_close"))
                if close <= 0 or future <= 0:
                    continue
                x_values.append([_to_float(row.get(column), 0.0) for column in columns])
                y_values.append(1 if future > close else 0)
        key = f"D{horizon}"
        if len(x_values) > 5000:
            step = max(1, len(x_values) // 5000)
            x_values = x_values[::step][:5000]
            y_values = y_values[::step][:5000]
        if len(set(y_values)) < 2 or len(x_values) < 20:
            result[key] = []
            continue
        try:
            scores = mutual_info_classif(x_values, y_values, random_state=42)
        except Exception as exc:
            warnings.append(f"{key}: mutual_info failed: {exc}")
            result[key] = []
            continue
        ranked = sorted(
            (
                {
                    "horizon": key,
                    "feature": column,
                    "score": _round(score, 6),
                    "keep": "YES",
                }
                for column, score in zip(columns, scores, strict=True)
            ),
            key=lambda item: (-float(item["score"]), str(item["feature"])),
        )
        result[key] = ranked
    return result, warnings


def _select_features(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    selection = config.get("selection", {})
    if not isinstance(selection, dict):
        selection = {}
    max_missing = _to_float(selection.get("max_missing_pct"), 0.25)
    corr_threshold = _to_float(selection.get("corr_threshold"), 0.95)
    top_n = max(1, int(selection.get("mutual_information_top_n", 120) or 120))
    selection_rows = _sample_rows(rows, 5000)
    candidates = _candidate_feature_columns(selection_rows)
    after_nan = [
        column
        for column in candidates
        if _missing_ratio(selection_rows, column) <= max_missing
    ]
    dropped_constant: list[str] = []
    if bool(selection.get("drop_constant", True)):
        nonconstant = []
        for column in after_nan:
            if _constant(selection_rows, column):
                dropped_constant.append(column)
            else:
                nonconstant.append(column)
        after_constant = nonconstant
    else:
        after_constant = after_nan
    after_corr, dropped_corr = _correlation_prune(selection_rows, after_constant, corr_threshold)
    mi_by_horizon: dict[str, list[dict[str, Any]]] = {}
    warnings: list[str] = []
    selected = after_corr
    if bool(selection.get("enabled", True)):
        mi_by_horizon, warnings = _mutual_information_scores(selection_rows, after_corr)
        selected_set: set[str] = set()
        if bool(selection.get("per_horizon_selection", True)):
            for ranking in mi_by_horizon.values():
                selected_set.update(str(item["feature"]) for item in ranking[:top_n])
        else:
            combined: dict[str, float] = defaultdict(float)
            for ranking in mi_by_horizon.values():
                for item in ranking:
                    combined[str(item["feature"])] += float(item["score"])
            selected_set.update(
                feature
                for feature, _score in sorted(combined.items(), key=lambda item: (-item[1], item[0]))[:top_n]
            )
        if selected_set:
            selected = [column for column in after_corr if column in selected_set]
    for column in PINNED_FEATURE_COLUMNS:
        if column in after_nan and column not in selected:
            selected.append(column)
    return {
        "features_total": len(candidates),
        "features_after_nan": len(after_nan),
        "features_after_constant": len(after_constant),
        "features_after_corr": len(after_corr),
        "features_selected": len(selected),
        "candidate_features": candidates,
        "selected_features": selected,
        "dropped_constant": dropped_constant,
        "dropped_corr": dropped_corr,
        "top_features_by_horizon": mi_by_horizon,
        "warnings": warnings,
    }


def build_features_v2(
    *,
    universe: str | Path,
    prices_dir: str | Path = "data/prices",
    context: str | Path = "storage/context/latest_market_context.json",
    indices_dir: str | Path = "data/indices",
    config_path: str | Path = "config/features.json",
) -> dict[str, Any]:
    config = load_features_config(config_path)
    groups = config.get("enabled_groups", {})
    if not isinstance(groups, dict):
        groups = {}
    universe_rows = _read_csv(universe)
    context_values = _market_context_values(context)
    index_returns = _load_index_returns(indices_dir)
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    missing_price_files: list[str] = []
    history_config = config.get("history", {})
    if not isinstance(history_config, dict):
        history_config = {}
    max_rows_per_asset = max(0, int(history_config.get("max_rows_per_asset", 1500) or 0))
    for asset in universe_rows:
        ticker = str(asset.get("ticker", "")).strip().upper()
        sector = str(asset.get("sector", "")).strip()
        if not ticker:
            continue
        price_file = _price_file_for_ticker(prices_dir, ticker)
        price_rows = _read_price_rows(price_file)
        if not price_rows:
            missing_price_files.append(ticker)
            continue
        rows.extend(
            _asset_feature_rows(
                ticker=ticker,
                sector=sector,
                price_rows=price_rows,
                index_returns=index_returns,
                context=context_values,
                groups=groups,
                max_rows=max_rows_per_asset,
            )
        )
    if not any(str(row.get("sector", "")).strip() for row in rows):
        warnings.append("sector data missing; sector features are empty")
    _add_sector_features(rows, groups)
    rows.sort(key=lambda item: (str(item.get("ticker", "")), str(item.get("date", ""))))
    selection = _select_features(rows, config) if rows else {
        "features_total": 0,
        "features_after_nan": 0,
        "features_after_constant": 0,
        "features_after_corr": 0,
        "features_selected": 0,
        "candidate_features": [],
        "selected_features": [],
        "dropped_constant": [],
        "dropped_corr": [],
        "top_features_by_horizon": {},
        "warnings": [],
    }
    warnings.extend(selection.get("warnings", []))
    selected = list(selection.get("selected_features", []))
    history_columns = ["date", "ticker", "sector", "_close", *selected]
    history_rows = [
        {column: row.get(column, "") for column in history_columns}
        for row in rows
    ]
    latest_by_ticker: dict[str, dict[str, Any]] = {}
    for row in rows:
        latest_by_ticker[str(row.get("ticker", ""))] = row
    latest_columns = ["ticker", "sector", "date", *selected]
    for column in COMPATIBILITY_COLUMNS:
        if column not in latest_columns:
            latest_columns.append(column)
    latest_rows = [
        {column: row.get(column, "") for column in latest_columns}
        for _ticker, row in sorted(latest_by_ticker.items())
    ]
    audit = {
        "schema_version": "feature_audit.v2",
        "feature_set": config.get("feature_set", "core_v2"),
        "enabled": bool(config.get("enabled", True)),
        "config": str(config_path),
        "universe": str(universe),
        "prices_dir": str(prices_dir),
        "context": str(context),
        "features_total": selection["features_total"],
        "features_after_nan": selection["features_after_nan"],
        "features_after_constant": selection["features_after_constant"],
        "features_after_corr": selection["features_after_corr"],
        "features_selected": selection["features_selected"],
        "assets": len(latest_rows),
        "rows": len(rows),
        "missing_price_files": sorted(set(missing_price_files)),
        "missing_price_files_count": len(set(missing_price_files)),
        "feature_groups": dict(groups),
        "feature_selection_summary": {
            "max_missing_pct": config.get("selection", {}).get("max_missing_pct"),
            "drop_constant": config.get("selection", {}).get("drop_constant"),
            "corr_threshold": config.get("selection", {}).get("corr_threshold"),
            "mutual_information_top_n": config.get("selection", {}).get("mutual_information_top_n"),
            "per_horizon_selection": config.get("selection", {}).get("per_horizon_selection"),
            "dropped_constant": selection["dropped_constant"][:50],
            "dropped_corr": selection["dropped_corr"][:50],
        },
        "top_features_by_horizon": selection["top_features_by_horizon"],
        "warnings": warnings,
        "history": {
            "max_rows_per_asset": max_rows_per_asset,
        },
    }
    return {
        "status": "OK" if rows and latest_rows else "FAIL",
        "feature_set": config.get("feature_set", "core_v2"),
        "config": config,
        "audit": audit,
        "feature_list": {
            "schema_version": "feature_list.v2",
            "feature_set": config.get("feature_set", "core_v2"),
            "features": selected,
            "features_total": selection["features_total"],
            "features_used": len(selected),
            "feature_groups": dict(groups),
        },
        "history_columns": history_columns,
        "history_rows": history_rows,
        "latest_columns": latest_columns,
        "latest_rows": latest_rows,
    }


def write_features_v2(
    *,
    universe: str | Path,
    prices_dir: str | Path = "data/prices",
    context: str | Path = "storage/context/latest_market_context.json",
    indices_dir: str | Path = "data/indices",
    config_path: str | Path = "config/features.json",
    matrix_output: str | Path = DEFAULT_MATRIX_OUTPUT,
    history_output: str | Path = DEFAULT_HISTORY_OUTPUT,
    audit_output: str | Path = DEFAULT_AUDIT_OUTPUT,
    feature_list_output: str | Path = DEFAULT_LIST_OUTPUT,
) -> dict[str, Any]:
    payload = build_features_v2(
        universe=universe,
        prices_dir=prices_dir,
        context=context,
        indices_dir=indices_dir,
        config_path=config_path,
    )
    _write_csv(matrix_output, payload["latest_rows"], payload["latest_columns"])
    _write_csv(history_output, payload["history_rows"], payload["history_columns"])
    audit = dict(payload["audit"])
    audit.update(
        {
            "matrix": str(matrix_output),
            "history_matrix": str(history_output),
            "feature_audit": str(audit_output),
            "feature_list": str(feature_list_output),
        }
    )
    feature_list = dict(payload["feature_list"])
    feature_list.update(
        {
            "matrix": str(matrix_output),
            "history_matrix": str(history_output),
            "feature_audit": str(audit_output),
            "feature_list": str(feature_list_output),
        }
    )
    _write_json(audit_output, audit)
    _write_json(feature_list_output, feature_list)
    return {
        "schema_version": "features_v2_result.v1",
        "status": payload["status"],
        "feature_set": payload["feature_set"],
        "rows": len(payload["latest_rows"]),
        "assets": len(payload["latest_rows"]),
        "history_rows": len(payload["history_rows"]),
        "columns": payload["latest_columns"],
        "features_total": audit["features_total"],
        "features_used": audit["features_selected"],
        "feature_groups": audit["feature_groups"],
        "feature_selection_summary": audit["feature_selection_summary"],
        "warnings": audit["warnings"],
        "missing_price_files": audit["missing_price_files"],
        "missing_price_files_count": audit["missing_price_files_count"],
        "output": str(matrix_output),
        "matrix": str(matrix_output),
        "history_matrix": str(history_output),
        "feature_audit": str(audit_output),
        "feature_list": str(feature_list_output),
        "audit": audit,
    }


def load_latest_feature_audit(path: str | Path = DEFAULT_AUDIT_OUTPUT) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def render_feature_audit(payload: dict[str, Any]) -> str:
    audit = payload.get("audit", payload)
    line = "-" * 80
    top_by_horizon = audit.get("top_features_by_horizon", {})
    rows: list[dict[str, Any]] = []
    if isinstance(top_by_horizon, dict):
        for horizon, items in top_by_horizon.items():
            if not isinstance(items, list):
                continue
            for item in items[:5]:
                if isinstance(item, dict):
                    rows.append(item)
    lines = [
        "FEATURE AUDIT",
        line,
        f"feature_set          {audit.get('feature_set', '-')}",
        f"features_total       {audit.get('features_total', 0)}",
        f"features_after_nan   {audit.get('features_after_nan', 0)}",
        f"features_after_corr  {audit.get('features_after_corr', 0)}",
        f"features_selected    {audit.get('features_selected', 0)}",
        f"assets               {audit.get('assets', 0)}",
        f"rows                 {audit.get('rows', 0)}",
        "",
        "TOP FEATURES BY HORIZON",
        line,
        f"{'HZ':<4} {'FEATURE':<26} {'SCORE':>8} KEEP",
    ]
    for row in rows[:20]:
        lines.append(
            f"{str(row.get('horizon', '-')):<4} "
            f"{str(row.get('feature', '-')):<26} "
            f"{float(row.get('score', 0.0)):>8.4f} "
            f"{row.get('keep', 'YES')}"
        )
    if not rows:
        lines.append("No mutual information ranking available.")
    return "\n".join(lines)
