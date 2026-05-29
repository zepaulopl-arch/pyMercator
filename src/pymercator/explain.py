from __future__ import annotations

from pymercator.domain import AssetDecision, ExecutionStatus


def _joined_reasons(decision: AssetDecision) -> str:
    reasons = (
        *decision.ranking.reasons,
        *decision.validation.reasons,
        *decision.permission.reasons,
    )
    return " | ".join(reasons).lower()


def decision_codes(decision: AssetDecision) -> tuple[str, ...]:
    reason_text = _joined_reasons(decision)
    codes: list[str] = []

    if "headline factor" in reason_text:
        codes.append("HEADLINE")

    if "sector factor" in reason_text or "sector sensitivity" in reason_text:
        codes.append("SECTOR")

    if "caps permission" in reason_text:
        codes.append("CAP")

    if "context score below" in reason_text:
        codes.append("CTX_LOW")

    if "market regime denied" in reason_text:
        codes.append("REGIME_DENY")

    if "regime or universe requires caution" in reason_text:
        codes.append("CAUTION")

    if "rr below" in reason_text:
        codes.append("RR_LOW")

    if "atr above" in reason_text:
        codes.append("ATR_HIGH")

    if "volatility above" in reason_text:
        codes.append("VOL_HIGH")

    if "liquidity below" in reason_text:
        codes.append("LIQ_LOW")

    if "missing entry" in reason_text:
        codes.append("NO_ENTRY")

    if "missing stop" in reason_text:
        codes.append("NO_STOP")

    if "missing target" in reason_text:
        codes.append("NO_TARGET")

    if codes:
        return tuple(dict.fromkeys(codes))

    if decision.permission.status == ExecutionStatus.READY:
        return ("OK",)

    if decision.permission.status == ExecutionStatus.WATCH:
        return ("CAUTION",)

    if decision.permission.status == ExecutionStatus.MANUAL_ONLY:
        return ("MANUAL_ONLY",)

    if decision.permission.status == ExecutionStatus.INVALID:
        return ("INVALID",)

    if decision.permission.status == ExecutionStatus.BLOCKED:
        return ("BLOCKED",)

    return ("UNKNOWN",)


def decision_label(decision: AssetDecision) -> str:
    return "+".join(decision_codes(decision))
