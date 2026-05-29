from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def _read_price_file(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    data = pd.read_csv(path)
    data.columns = [str(column).lower() for column in data.columns]

    if "date" not in data.columns or "close" not in data.columns:
        return pd.DataFrame()

    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["close"] = pd.to_numeric(data["close"], errors="coerce")
    data = data.dropna(subset=["date", "close"])
    data = data[data["close"] > 0]
    data = data.sort_values("date")

    return data


def _last_return(data: pd.DataFrame, window: int) -> float:
    if len(data) <= window:
        return 0.0

    last = float(data["close"].iloc[-1])
    previous = float(data["close"].iloc[-window - 1])

    if previous <= 0:
        return 0.0

    return round(((last / previous) - 1.0) * 100.0, 2)


def _annualized_volatility(data: pd.DataFrame, window: int = 20) -> float:
    if len(data) <= window:
        return 0.0

    returns = data["close"].pct_change().dropna().tail(window)

    if returns.empty:
        return 0.0

    return round(float(returns.std() * (252**0.5) * 100.0), 2)


def _sma_position(data: pd.DataFrame, window: int = 20) -> float:
    if len(data) < window:
        return 0.0

    last = float(data["close"].iloc[-1])
    sma = float(data["close"].tail(window).mean())

    if sma <= 0:
        return 0.0

    return round(((last / sma) - 1.0) * 100.0, 2)


def _market_trend(ibov: pd.DataFrame) -> str:
    ret_20 = _last_return(ibov, 20)
    sma_position = _sma_position(ibov, 20)

    if ret_20 >= 3.0 and sma_position >= 1.0:
        return "UP"

    if ret_20 <= -3.0 and sma_position <= -1.0:
        return "DOWN"

    return "CHOPPY"


def _market_volatility(ibov: pd.DataFrame) -> str:
    vol = _annualized_volatility(ibov, 20)

    if vol >= 28.0:
        return "HIGH"

    if vol <= 12.0 and vol > 0:
        return "LOW"

    return "NORMAL"


def build_auto_market_context(indices_dir: str | Path) -> dict[str, Any]:
    root = Path(indices_dir)

    ibov = _read_price_file(root / "^BVSP.csv")
    brent = _read_price_file(root / "BZ=F.csv")
    usdbrl = _read_price_file(root / "USDBRL=X.csv")

    headline_tags: list[str] = []
    notes: list[str] = []

    market_trend = _market_trend(ibov)
    market_volatility = _market_volatility(ibov)

    ibov_ret_5 = _last_return(ibov, 5)
    ibov_ret_20 = _last_return(ibov, 20)
    ibov_vol_20 = _annualized_volatility(ibov, 20)

    brent_ret_5 = _last_return(brent, 5)
    brent_ret_20 = _last_return(brent, 20)

    usdbrl_ret_5 = _last_return(usdbrl, 5)
    usdbrl_ret_20 = _last_return(usdbrl, 20)

    if market_trend == "UP" and market_volatility != "HIGH":
        headline_tags.append("RISK_ON")
        notes.append("IBOV trend supports risk-on posture")

    if market_trend == "DOWN" or market_volatility == "HIGH":
        headline_tags.append("RISK_OFF")
        notes.append("IBOV trend/volatility supports caution")

    if brent_ret_5 >= 5.0 or brent_ret_20 >= 10.0:
        headline_tags.extend(["OIL", "OIL_STRESS"])
        notes.append("Brent move indicates oil stress")

    if usdbrl_ret_5 >= 3.0 or usdbrl_ret_20 >= 6.0:
        headline_tags.extend(["BRL", "FX_STRESS"])
        notes.append("USD/BRL move indicates FX stress")

    if not headline_tags:
        notes.append("No major automatic macro stress detected")

    unique_tags = sorted(set(headline_tags))

    return {
        "headline_tags": unique_tags,
        "market_trend": market_trend,
        "market_volatility": market_volatility,
        "notes": "; ".join(notes),
        "source": "auto_indices",
        "metrics": {
            "ibov_return_5d_pct": ibov_ret_5,
            "ibov_return_20d_pct": ibov_ret_20,
            "ibov_volatility_20d_annualized_pct": ibov_vol_20,
            "brent_return_5d_pct": brent_ret_5,
            "brent_return_20d_pct": brent_ret_20,
            "usdbrl_return_5d_pct": usdbrl_ret_5,
            "usdbrl_return_20d_pct": usdbrl_ret_20,
        },
    }


def write_auto_market_context(
    *,
    indices_dir: str | Path,
    output: str | Path,
) -> dict[str, Any]:
    context = build_auto_market_context(indices_dir)

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(context, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "indices_dir": str(indices_dir),
        "output": str(output_path),
        "headline_tags": context["headline_tags"],
        "market_trend": context["market_trend"],
        "market_volatility": context["market_volatility"],
        "notes": context["notes"],
        "metrics": context["metrics"],
    }
