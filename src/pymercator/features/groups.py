from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    group: str
    source: str
    horizon_relevance: tuple[str, ...] = ("D5", "D20", "D60")
    enabled: bool = True
    description: str = ""


EXCLUDED_COLUMNS = {
    "date",
    "ticker",
    "_close",
    "close",
    "open",
    "high",
    "low",
    "volume",
}


CANONICAL_REPLACEMENTS = {
    "return_1d": "ret_1d",
    "return_5d": "ret_5d",
    "return_20d": "ret_20d",
    "atr_pct": "atr_14_pct",
    "volatility_20d": "realized_vol_20",
    "trend_score": "ma_stack_score",
    "momentum_score": "rsi_14",
}


def canonical_name(name: str) -> str:
    return CANONICAL_REPLACEMENTS.get(name, name)


def is_duplicate_alias(name: str) -> bool:
    return name in CANONICAL_REPLACEMENTS


def is_target_column(name: str) -> bool:
    n = name.lower()
    return n.startswith("target_") or n in {"y", "label"}


def is_excluded_column(name: str) -> bool:
    return name in EXCLUDED_COLUMNS or is_target_column(name)


def infer_horizons(name: str) -> tuple[str, ...]:
    n = name.lower()
    hs = []

    if "_5" in n or "5d" in n or "d5" in n:
        hs.append("D5")
    if "_20" in n or "20d" in n or "d20" in n:
        hs.append("D20")
    if "_60" in n or "60d" in n or "d60" in n:
        hs.append("D60")

    if not hs:
        return ("D5", "D20", "D60")

    return tuple(dict.fromkeys(hs))


def classify_group(name: str) -> str:
    n = name.lower()

    if n == "sector" or n.startswith("sector_") or "sector" in n:
        return "sector"

    if n.startswith("context") or n.startswith("news") or "context" in n or "headline" in n:
        return "context"

    if n.startswith("market_"):
        if "vol" in n:
            return "volatility"
        if "trend" in n:
            return "trend"
        return "macro"

    if "narrow_range" in n:
        return "volatility"

    if any(x in n for x in [
        "ret", "return", "log_ret", "drawdown", "distance_from",
        "new_high", "new_low", "breakout", "breakdown",
        "range_compression", "price"
    ]):
        return "price"

    if any(x in n for x in [
        "ema", "ma_", "ma_stack", "adx", "macd", "trend",
        "slope", "cci", "williams"
    ]):
        return "trend"

    if any(x in n for x in [
        "rsi", "momentum", "mfi", "obv", "volume_zscore",
        "volume_ratio", "dollar_volume", "liquidity"
    ]):
        return "momentum"

    if any(x in n for x in [
        "vol", "atr", "bollinger", "squeeze", "beta",
        "corr", "regime", "compression"
    ]):
        return "volatility"

    if any(x in n for x in [
        "juros", "selic", "ipca", "copom", "dolar", "usd", "macro",
        "cdi", "fed", "interest", "inflation"
    ]):
        return "macro"

    return "unknown"


def infer_source(name: str, group: str) -> str:
    if group in {"context", "macro"}:
        return group
    if group == "sector":
        return "sector"
    return "prices"


def make_spec(name: str) -> FeatureSpec:
    group = classify_group(name)
    return FeatureSpec(
        name=name,
        group=group,
        source=infer_source(name, group),
        horizon_relevance=infer_horizons(name),
        enabled=not is_excluded_column(name),
        description=f"Auto-registered feature: {name}",
    )
