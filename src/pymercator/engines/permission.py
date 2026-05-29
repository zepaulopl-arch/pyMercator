from __future__ import annotations

from typing import Any

from pymercator.domain import (
    ExecutionPermissionResult,
    ExecutionStatus,
    MarketRegimeResult,
    Permission,
    RankingRow,
    TradeValidationResult,
    UniverseHealthResult,
)


def decide_execution_permission(
    *,
    ticker: str,
    profile: str,
    ranking: RankingRow,
    validation: TradeValidationResult,
    regime: MarketRegimeResult,
    universe: UniverseHealthResult,
    policy: dict[str, Any],
) -> ExecutionPermissionResult:
    reasons: list[str] = []
    profile_policy = policy["profiles"][profile]

    max_position_factor = float(profile_policy["max_position_factor"])
    max_position_factor *= regime.exposure_factor

    if regime.permission == Permission.DENY:
        return ExecutionPermissionResult(
            ticker=ticker,
            status=ExecutionStatus.BLOCKED,
            max_position_factor=0.0,
            requires_human_confirmation=True,
            reasons=("market regime denied operation", *regime.reasons),
        )

    if universe.permission == Permission.DENY:
        return ExecutionPermissionResult(
            ticker=ticker,
            status=ExecutionStatus.BLOCKED,
            max_position_factor=0.0,
            requires_human_confirmation=True,
            reasons=("universe health denied operation", *universe.reasons),
        )

    if not validation.valid:
        return ExecutionPermissionResult(
            ticker=ticker,
            status=ExecutionStatus.BLOCKED,
            max_position_factor=0.0,
            requires_human_confirmation=True,
            reasons=validation.reasons,
        )

    if ranking.context_score < 55:
        return ExecutionPermissionResult(
            ticker=ticker,
            status=ExecutionStatus.WATCH,
            max_position_factor=0.0,
            requires_human_confirmation=True,
            reasons=("context score below operational threshold",),
        )

    headline_rule = policy["headline_risk"][regime.headline_risk.value]
    permission_cap = str(headline_rule["permission_cap"]).upper()

    if permission_cap == "WATCH":
        reasons.append(f"headline risk {regime.headline_risk.value} caps permission at WATCH")
        return ExecutionPermissionResult(
            ticker=ticker,
            status=ExecutionStatus.WATCH,
            max_position_factor=round(max_position_factor, 2),
            requires_human_confirmation=True,
            reasons=tuple(reasons),
        )

    if regime.permission == Permission.CAUTION or universe.permission == Permission.CAUTION:
        reasons.append("regime or universe requires caution")
        return ExecutionPermissionResult(
            ticker=ticker,
            status=ExecutionStatus.WATCH,
            max_position_factor=round(max_position_factor, 2),
            requires_human_confirmation=True,
            reasons=tuple(reasons),
        )

    return ExecutionPermissionResult(
        ticker=ticker,
        status=ExecutionStatus.READY,
        max_position_factor=round(max_position_factor, 2),
        requires_human_confirmation=True,
        reasons=("valid setup; human confirmation still required",),
    )