from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from pymercator.data.universe_csv import load_universe_csv
from pymercator.policy import load_policy


def _code_join(codes: list[str]) -> str:
    if not codes:
        return "OK"
    return "+".join(codes)


def diagnose_universe_csv(
    *,
    path: str | Path,
    policy_path: str | Path = "config/policy.json",
) -> dict[str, Any]:
    policy = load_policy(policy_path)
    assets = load_universe_csv(path)

    universe_policy = policy["universe_health"]
    min_volume = float(universe_policy["min_avg_volume_brl"])
    max_volatility = float(universe_policy["max_volatility_pct"])
    max_atr = float(universe_policy["max_atr_pct"])
    min_assets = int(universe_policy["min_valid_assets"])

    weak_trend_threshold = 45.0
    weak_momentum_threshold = 45.0

    diagnostics: list[dict[str, Any]] = []

    liquidity_low = 0
    volatility_high = 0
    atr_high = 0
    weak_trend = 0
    weak_momentum = 0
    missing_trade_plan = 0

    for asset in assets:
        codes: list[str] = []

        if asset.avg_volume_brl < min_volume:
            codes.append("LIQ_LOW")
            liquidity_low += 1

        if asset.volatility_pct > max_volatility:
            codes.append("VOL_HIGH")
            volatility_high += 1

        if asset.atr_pct > max_atr:
            codes.append("ATR_HIGH")
            atr_high += 1

        if asset.trend_score < weak_trend_threshold:
            codes.append("WEAK_TREND")
            weak_trend += 1

        if asset.momentum_score < weak_momentum_threshold:
            codes.append("WEAK_MOM")
            weak_momentum += 1

        if asset.entry is None or asset.stop is None or asset.target is None:
            codes.append("NO_PLAN")
            missing_trade_plan += 1

        diagnostics.append(
            {
                "ticker": asset.ticker,
                "sector": asset.sector,
                "avg_volume_brl": asset.avg_volume_brl,
                "volatility_pct": asset.volatility_pct,
                "atr_pct": asset.atr_pct,
                "trend_score": asset.trend_score,
                "momentum_score": asset.momentum_score,
                "codes": codes,
                "label": _code_join(codes),
            }
        )

    sectors = Counter(asset.sector for asset in assets)
    top_sector = sectors.most_common(1)[0] if sectors else ("-", 0)
    concentration_pct = (top_sector[1] / len(assets)) if assets else 0.0

    if len(assets) < min_assets:
        asset_count_status = "TOO_SMALL"
    else:
        asset_count_status = "OK"

    if concentration_pct >= 0.50:
        concentration_status = "HIGH"
    elif concentration_pct >= 0.35:
        concentration_status = "MODERATE"
    else:
        concentration_status = "LOW"

    warning_count = sum(1 for item in diagnostics if item["codes"])

    if not assets:
        data_status = "FAIL"
    elif asset_count_status == "TOO_SMALL":
        data_status = "WARN_SMALL_UNIVERSE"
    elif warning_count == 0 and concentration_status == "LOW":
        data_status = "PASS"
    else:
        data_status = "PASS_WITH_WARNINGS"

    return {
        "path": str(path),
        "policy": str(policy_path),
        "assets": len(assets),
        "min_assets": min_assets,
        "data_status": data_status,
        "asset_count_status": asset_count_status,
        "warning_count": warning_count,
        "liquidity_low": liquidity_low,
        "volatility_high": volatility_high,
        "atr_high": atr_high,
        "weak_trend": weak_trend,
        "weak_momentum": weak_momentum,
        "missing_trade_plan": missing_trade_plan,
        "sector_concentration": {
            "status": concentration_status,
            "top_sector": top_sector[0],
            "top_sector_count": top_sector[1],
            "top_sector_pct": round(concentration_pct * 100.0, 2),
            "sectors": dict(sorted(sectors.items())),
        },
        "diagnostics": diagnostics,
    }
