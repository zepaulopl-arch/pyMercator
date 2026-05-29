from __future__ import annotations

from collections import Counter
from typing import Any

from pymercator.domain import AssetSnapshot, Permission, UniverseHealth, UniverseHealthResult


def _is_valid_asset(asset: AssetSnapshot) -> bool:
    return bool(asset.ticker) and asset.last_close > 0


def _is_healthy_asset(asset: AssetSnapshot, policy: dict[str, Any]) -> bool:
    rules = policy["universe_health"]

    if not _is_valid_asset(asset):
        return False

    if asset.avg_volume_brl < float(rules["min_avg_volume_brl"]):
        return False

    if asset.volatility_pct > float(rules["max_volatility_pct"]):
        return False

    if asset.atr_pct > float(rules["max_atr_pct"]):
        return False

    if asset.trend_score < 50:
        return False

    if asset.momentum_score < 45:
        return False

    return True


def _sector_concentration(healthy_assets: list[AssetSnapshot]) -> str:
    if not healthy_assets:
        return "UNKNOWN"

    counts = Counter(asset.sector for asset in healthy_assets)
    top_count = max(counts.values())
    share = top_count / len(healthy_assets)

    if share >= 0.60:
        return "HIGH"
    if share >= 0.40:
        return "MEDIUM"
    return "LOW"


def evaluate_universe_health(
    *,
    universe_name: str,
    assets: list[AssetSnapshot],
    policy: dict[str, Any],
) -> UniverseHealthResult:
    valid_assets = [asset for asset in assets if _is_valid_asset(asset)]
    healthy_assets = [asset for asset in valid_assets if _is_healthy_asset(asset, policy)]

    total = len(assets)
    valid = len(valid_assets)
    healthy = len(healthy_assets)

    reasons: list[str] = []

    if total == 0:
        return UniverseHealthResult(
            universe_name=universe_name,
            total_assets=0,
            valid_assets=0,
            healthy_assets=0,
            health=UniverseHealth.BROKEN,
            breadth_label="NO_DATA",
            sector_concentration="UNKNOWN",
            permission=Permission.DENY,
            reasons=("empty universe",),
        )

    healthy_pct = healthy / total
    rules = policy["universe_health"]

    if valid < int(rules["min_valid_assets"]):
        health = UniverseHealth.BROKEN
        permission = Permission.DENY
        breadth = "BROKEN"
        reasons.append("not enough valid assets")
    elif healthy_pct >= float(rules["healthy_pct_broad"]):
        health = UniverseHealth.BROAD
        permission = Permission.ALLOW
        breadth = "BROAD"
        reasons.append("many healthy assets")
    elif healthy_pct >= float(rules["healthy_pct_normal"]):
        health = UniverseHealth.NORMAL
        permission = Permission.ALLOW
        breadth = "NORMAL"
        reasons.append("normal quantity of healthy assets")
    elif healthy_pct >= float(rules["healthy_pct_narrow"]):
        health = UniverseHealth.NARROW
        permission = Permission.CAUTION
        breadth = "WEAK"
        reasons.append("few healthy assets")
    else:
        health = UniverseHealth.BROKEN
        permission = Permission.DENY
        breadth = "BROKEN"
        reasons.append("too few healthy assets")

    concentration = _sector_concentration(healthy_assets)
    if concentration == "HIGH":
        reasons.append("healthy assets are concentrated in one sector")

    return UniverseHealthResult(
        universe_name=universe_name,
        total_assets=total,
        valid_assets=valid,
        healthy_assets=healthy,
        health=health,
        breadth_label=breadth,
        sector_concentration=concentration,
        permission=permission,
        reasons=tuple(reasons),
    )