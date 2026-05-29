from __future__ import annotations

from typing import Any

from pymercator.domain import HeadlineRisk, MarketRegime, MarketRegimeResult, Permission


def normalize_headline_risk(value: str) -> HeadlineRisk:
    normalized = value.strip().upper()
    try:
        return HeadlineRisk(normalized)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in HeadlineRisk)
        raise ValueError(f"Invalid headline risk: {value}. Allowed: {allowed}") from exc


def classify_market_regime(
    *,
    headline_risk: str,
    headline_tags: list[str] | None,
    market_trend: str,
    market_volatility: str,
    policy: dict[str, Any],
) -> MarketRegimeResult:
    risk = normalize_headline_risk(headline_risk)
    tags = tuple(tag.strip().upper() for tag in (headline_tags or []) if tag.strip())

    trend = market_trend.strip().upper()
    volatility = market_volatility.strip().upper()

    reasons: list[str] = []

    if risk == HeadlineRisk.EXTREME:
        regime = MarketRegime.CRISIS
        permission = Permission.DENY
        reasons.append("headline risk is EXTREME")
    elif risk == HeadlineRisk.ACTIVE:
        regime = MarketRegime.EVENT_RISK
        permission = Permission.CAUTION
        reasons.append("headline risk is ACTIVE")
    elif trend == "DOWN" and volatility == "HIGH":
        regime = MarketRegime.RISK_OFF
        permission = Permission.CAUTION
        reasons.append("market trend DOWN with HIGH volatility")
    elif trend == "UP" and volatility in {"LOW", "NORMAL"}:
        regime = MarketRegime.RISK_ON
        permission = Permission.ALLOW
        reasons.append("market trend UP with acceptable volatility")
    elif trend == "CHOPPY":
        regime = MarketRegime.CHOPPY
        permission = Permission.CAUTION
        reasons.append("market trend is CHOPPY")
    else:
        regime = MarketRegime.UNKNOWN
        permission = Permission.UNKNOWN
        reasons.append("market regime could not be classified")

    headline_policy = policy["headline_risk"][risk.value]

    return MarketRegimeResult(
        regime=regime,
        permission=permission,
        headline_risk=risk,
        headline_tags=tags,
        score_factor=float(headline_policy["score_factor"]),
        exposure_factor=float(headline_policy["exposure_factor"]),
        reasons=tuple(reasons),
    )