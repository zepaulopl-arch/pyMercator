from __future__ import annotations

from typing import Any


def normalize_horizon_scores(scores: dict[str, Any]) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for key, value in scores.items():
        try:
            normalized[str(key).upper()] = float(value)
        except (TypeError, ValueError):
            continue
    return normalized


def horizon_spread(scores: dict[str, Any]) -> float:
    values = list(normalize_horizon_scores(scores).values())
    if not values:
        return 0.0
    return round(max(values) - min(values), 4)


def dominance_strength(scores: dict[str, Any]) -> str:
    spread = horizon_spread(scores)
    if spread < 3:
        return "NONE"
    if spread < 7:
        return "WEAK"
    if spread < 12:
        return "MODERATE"
    return "STRONG"


def horizon_alignment(scores: dict[str, Any]) -> str:
    normalized = normalize_horizon_scores(scores)
    values = list(normalized.values())
    if not values:
        return "-"

    if all(value >= 60 for value in values):
        return "ALIGNED_STRONG"
    if all(value < 52 for value in values):
        return "FLAT_WEAK"
    if horizon_spread(normalized) < 3:
        return "FLAT"

    d5 = normalized.get("D5", 0.0)
    d20 = normalized.get("D20", 0.0)
    d60 = normalized.get("D60", 0.0)
    if d5 >= 60 and d20 < 52 and d60 < 52:
        return "SHORT_ONLY"
    if d20 >= 60 and d5 < 52 and d60 < 52:
        return "MID_ONLY"
    if d60 >= 60 and d5 < 52 and d20 < 52:
        return "LONG_ONLY"
    return "DIVERGENT"
