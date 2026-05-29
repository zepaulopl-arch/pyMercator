from __future__ import annotations

from typing import Any

from pymercator.domain import AssetSnapshot, MarketRegimeResult, RankingRow


def _volatility_score(asset: AssetSnapshot) -> float:
    score = 100.0 - (asset.volatility_pct * 10.0)
    return max(0.0, min(100.0, score))


def _signal_from_score(score: float) -> str:
    if score >= 70:
        return "BUY"
    if score >= 55:
        return "NEUTRAL"
    return "AVOID"


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _sector_sensitivity_factor(
    *,
    sector: str,
    headline_tags: tuple[str, ...],
    policy: dict[str, Any],
) -> tuple[float, tuple[str, ...]]:
    sensitivity = policy.get("sector_sensitivity", {})

    if not sensitivity.get("enabled", False):
        return 1.0, ()

    rules = sensitivity.get("rules", {})
    default_factor = float(sensitivity.get("default_factor", 1.0))

    factors: list[float] = []
    matched_tags: list[str] = []

    for tag in headline_tags:
        normalized_tag = tag.upper()
        tag_rules = rules.get(normalized_tag)

        if not tag_rules:
            continue

        factor = float(tag_rules.get(sector, default_factor))
        factors.append(factor)
        matched_tags.append(normalized_tag)

    if not factors:
        return default_factor, ()

    average_factor = sum(factors) / len(factors)
    tag_text = ",".join(matched_tags)
    reason = f"sector sensitivity {sector}={average_factor:.2f} tags={tag_text}"

    return average_factor, (reason,)


def _context_factor(
    *,
    asset: AssetSnapshot,
    regime: MarketRegimeResult,
    policy: dict[str, Any],
) -> tuple[float, tuple[str, ...]]:
    sensitivity = policy.get("sector_sensitivity", {})
    min_factor = float(sensitivity.get("min_context_factor", 0.35))
    max_factor = float(sensitivity.get("max_context_factor", 1.20))

    sector_factor, sector_reasons = _sector_sensitivity_factor(
        sector=asset.sector,
        headline_tags=regime.headline_tags,
        policy=policy,
    )

    factor = regime.score_factor * sector_factor
    factor = _clamp(factor, min_factor, max_factor)

    reasons: list[str] = []

    if regime.score_factor < 1.0:
        reasons.append(f"headline factor {regime.score_factor:.2f}")

    if sector_factor != 1.0:
        reasons.append(f"sector factor {sector_factor:.2f}")

    reasons.extend(sector_reasons)

    return round(factor, 4), tuple(reasons)


def rank_assets(
    *,
    assets: list[AssetSnapshot],
    regime: MarketRegimeResult,
    policy: dict[str, Any],
) -> list[RankingRow]:
    weights = policy["ranking"]["weights"]
    rows: list[RankingRow] = []

    for asset in assets:
        raw = (
            asset.trend_score * float(weights["trend_score"])
            + asset.momentum_score * float(weights["momentum_score"])
            + asset.liquidity_score * float(weights["liquidity_score"])
            + asset.quality_score * float(weights["quality_score"])
            + asset.news_score * float(weights["news_score"])
            + _volatility_score(asset) * float(weights["volatility_score"])
        )

        factor, factor_reasons = _context_factor(
            asset=asset,
            regime=regime,
            policy=policy,
        )

        context_score = raw * factor
        reasons: list[str] = list(factor_reasons)

        if asset.avg_volume_brl <= 0:
            reasons.append("missing volume")

        rows.append(
            RankingRow(
                ticker=asset.ticker,
                sector=asset.sector,
                raw_score=round(raw, 2),
                context_score=round(context_score, 2),
                context_factor=factor,
                rank=0,
                raw_signal=_signal_from_score(raw),
                context_signal=_signal_from_score(context_score),
                reasons=tuple(reasons),
            )
        )

    rows.sort(key=lambda row: row.context_score, reverse=True)

    ranked: list[RankingRow] = []
    for index, row in enumerate(rows, start=1):
        ranked.append(
            RankingRow(
                ticker=row.ticker,
                sector=row.sector,
                raw_score=row.raw_score,
                context_score=row.context_score,
                context_factor=row.context_factor,
                rank=index,
                raw_signal=row.raw_signal,
                context_signal=row.context_signal,
                reasons=row.reasons,
            )
        )

    return ranked
