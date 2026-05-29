from __future__ import annotations

from typing import Any

from pymercator.domain import AssetSnapshot, ExecutionStatus, TradeValidationResult


def validate_trade(
    *,
    asset: AssetSnapshot,
    profile: str,
    policy: dict[str, Any],
) -> TradeValidationResult:
    profile_policy = policy["profiles"][profile]
    validation_policy = policy["trade_validation"]

    reasons: list[str] = []

    entry = asset.entry
    stop = asset.stop
    target = asset.target

    if entry is None:
        reasons.append("missing entry")
    if stop is None:
        reasons.append("missing stop")
    if target is None:
        reasons.append("missing target")

    rr: float | None = None

    if entry is not None and stop is not None and target is not None:
        risk = entry - stop
        reward = target - entry

        if risk <= 0:
            reasons.append("invalid stop: stop must be below entry for long trade")
        elif reward <= 0:
            reasons.append("invalid target: target must be above entry for long trade")
        else:
            rr = reward / risk

    liquidity_ok = asset.avg_volume_brl >= float(validation_policy["min_liquidity_brl"])
    volatility_ok = asset.volatility_pct <= float(validation_policy["max_volatility_pct"])
    atr_ok = asset.atr_pct <= float(validation_policy["max_atr_pct"])

    if not liquidity_ok:
        reasons.append("liquidity below minimum")

    if not volatility_ok:
        reasons.append("volatility above maximum")

    if not atr_ok:
        reasons.append("ATR above maximum")

    min_rr = float(profile_policy["min_rr"])
    if rr is None:
        reasons.append("RR unavailable")
    elif rr < min_rr:
        reasons.append(f"RR below minimum: {rr:.2f} < {min_rr:.2f}")

    valid = not reasons

    status = ExecutionStatus.READY if valid else ExecutionStatus.BLOCKED

    return TradeValidationResult(
        ticker=asset.ticker,
        valid=valid,
        entry=entry,
        stop=stop,
        target=target,
        rr=round(rr, 2) if rr is not None else None,
        liquidity_ok=liquidity_ok,
        volatility_ok=volatility_ok,
        atr_ok=atr_ok,
        status=status,
        reasons=tuple(reasons),
    )