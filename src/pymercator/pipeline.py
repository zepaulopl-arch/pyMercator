from __future__ import annotations

from pymercator.domain import AssetDecision, DailyReport, ExecutionStatus
from pymercator.engines.permission import decide_execution_permission
from pymercator.engines.ranking import rank_assets
from pymercator.engines.regime import classify_market_regime
from pymercator.engines.universe import evaluate_universe_health
from pymercator.engines.validation import validate_trade
from pymercator.loaders import load_universe_csv
from pymercator.policy import load_policy, normalize_profile


def _posture(
    decisions: list[AssetDecision],
    regime_status: str,
    universe_status: str,
) -> tuple[str, tuple[str, ...]]:
    ready = sum(1 for item in decisions if item.permission.status == ExecutionStatus.READY)
    watch = sum(1 for item in decisions if item.permission.status == ExecutionStatus.WATCH)

    reasons: list[str] = []

    if regime_status in {"DENY", "UNKNOWN"}:
        reasons.append("market regime is not permissive")
        return "STAND_ASIDE", tuple(reasons)

    if universe_status in {"DENY", "UNKNOWN"}:
        reasons.append("universe health is not permissive")
        return "STAND_ASIDE", tuple(reasons)

    if ready == 0 and watch == 0:
        reasons.append("no operational candidates")
        return "STAND_ASIDE", tuple(reasons)

    if ready == 0 and watch > 0:
        reasons.append("watch candidates exist but no ready trades")
        return "WATCH_ONLY", tuple(reasons)

    if ready <= 2:
        reasons.append("few ready candidates")
        return "SELECTIVE", tuple(reasons)

    return "NORMAL", ("multiple ready candidates",)


def run_daily_pipeline(
    *,
    universe_path: str,
    universe_name: str,
    profile: str,
    headline_risk: str,
    headline_tags: list[str],
    market_trend: str,
    market_volatility: str,
    policy_path: str = "config/policy.json",
) -> DailyReport:
    policy = load_policy(policy_path)
    normalized_profile = normalize_profile(profile)

    assets = load_universe_csv(universe_path)

    regime = classify_market_regime(
        headline_risk=headline_risk,
        headline_tags=headline_tags,
        market_trend=market_trend,
        market_volatility=market_volatility,
        policy=policy,
    )

    universe = evaluate_universe_health(
        universe_name=universe_name,
        assets=assets,
        policy=policy,
    )

    rankings = rank_assets(
        assets=assets,
        regime=regime,
        policy=policy,
    )

    asset_by_ticker = {asset.ticker: asset for asset in assets}

    decisions: list[AssetDecision] = []

    for ranking in rankings:
        asset = asset_by_ticker[ranking.ticker]

        validation = validate_trade(
            asset=asset,
            profile=normalized_profile,
            policy=policy,
        )

        permission = decide_execution_permission(
            ticker=asset.ticker,
            profile=normalized_profile,
            ranking=ranking,
            validation=validation,
            regime=regime,
            universe=universe,
            policy=policy,
        )

        decisions.append(
            AssetDecision(
                asset=asset,
                ranking=ranking,
                validation=validation,
                permission=permission,
            )
        )

    posture, reasons = _posture(
        decisions,
        regime.permission.value,
        universe.permission.value,
    )

    return DailyReport(
        universe_name=universe_name,
        profile=normalized_profile,
        market_regime=regime,
        universe_health=universe,
        decisions=tuple(decisions),
        posture=posture,
        reasons=reasons,
    )