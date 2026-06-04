from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pymercator.config_loader import deep_merge
from pymercator.domain import AssetDecision, AssetSnapshot
from pymercator.loaders import load_universe_csv
from pymercator.ui import muted_line, short_sector, truncate

DEFAULT_OBSERVATION_CONFIG: dict[str, Any] = {
    "enabled": True,
    "weights": {
        "trend": 0.35,
        "momentum": 0.30,
        "volatility_safety": 0.20,
        "atr_safety": 0.15,
    },
    "risk_penalty": {
        "vol_high": 10,
        "atr_high": 15,
    },
    "thresholds": {
        "obs_ready": 70.0,
        "watch": 55.0,
        "weak": 45.0,
        "trend_strong": 60.0,
        "momentum_strong": 60.0,
        "trend_watch": 50.0,
        "momentum_watch": 50.0,
        "vol_high": 55.0,
        "atr_high": 70.0,
        "vol_extreme": 85.0,
        "atr_extreme": 85.0,
        "vol_low": 35.0,
        "atr_low": 35.0,
    },
    "show_when_no_actionable": True,
    "max_candidates": 10,
    "sector_summary": True,
    "unsupervised": {
        "enabled": False,
        "method": "kmeans",
        "clusters": 5,
    },
}

OBS_CLASS_PRIORITY = {
    "OBS_FAVORABLE": 0,
    "MOM_HIGH_RISK": 1,
    "WATCH": 2,
    "LOW_RISK_WEAK": 3,
    "WEAK": 4,
    "DANGER": 5,
}


def load_observation_config(path: str | Path = "config/observation.json") -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except Exception:
        return json.loads(json.dumps(DEFAULT_OBSERVATION_CONFIG))
    if not isinstance(payload, dict):
        return json.loads(json.dumps(DEFAULT_OBSERVATION_CONFIG))
    return deep_merge(DEFAULT_OBSERVATION_CONFIG, payload)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _risk_values_are_scaled(values: list[float]) -> bool:
    if not values:
        return True
    return min(values) >= 0 and max(values) <= 100 and max(values) > 20


def _normalize_risk_values(values: list[float]) -> list[float]:
    if not values:
        return []
    if _risk_values_are_scaled(values):
        return [_clamp(value) for value in values]

    low = _quantile(values, 0.05)
    high = _quantile(values, 0.95)
    if high <= low:
        high = max(values)
        low = min(values)
    if high <= low:
        return [0.0 for _value in values]
    return [_clamp(((value - low) / (high - low)) * 100.0) for value in values]


def _weights(config: dict[str, Any]) -> dict[str, float]:
    raw = config.get("weights", {})
    if not isinstance(raw, dict):
        raw = {}
    weights = {
        "trend": _to_float(raw.get("trend", 0.35)),
        "momentum": _to_float(raw.get("momentum", 0.30)),
        "volatility_safety": _to_float(raw.get("volatility_safety", 0.20)),
        "atr_safety": _to_float(raw.get("atr_safety", 0.15)),
    }
    total = sum(weights.values()) or 1.0
    return {key: value / total for key, value in weights.items()}


def _risk_penalty(config: dict[str, Any], key: str) -> float:
    raw = config.get("risk_penalty", {})
    if not isinstance(raw, dict):
        return 0.0
    return _to_float(raw.get(key, 0.0))


def _thresholds(config: dict[str, Any]) -> dict[str, float]:
    raw = config.get("thresholds", {})
    if not isinstance(raw, dict):
        raw = {}
    defaults = DEFAULT_OBSERVATION_CONFIG["thresholds"]
    return {
        key: _to_float(raw.get(key), float(default))
        for key, default in defaults.items()
    }


def _asset_class(
    *,
    obs_index: float,
    trend: float,
    momentum: float,
    vol_high: bool,
    atr_high: bool,
    vol_extreme: bool,
    atr_extreme: bool,
    vol_low: bool,
    atr_low: bool,
    thresholds: dict[str, float],
) -> str:
    strong_opportunity = (
        trend >= thresholds["trend_strong"]
        and momentum >= thresholds["momentum_strong"]
    )
    weak_opportunity = (
        trend < thresholds["trend_watch"]
        and momentum < thresholds["momentum_watch"]
    )
    extreme_risk = vol_extreme or atr_extreme

    if extreme_risk and weak_opportunity:
        return "DANGER"
    if strong_opportunity and (vol_high or atr_high):
        return "MOM_HIGH_RISK"
    if obs_index >= thresholds["obs_ready"] and strong_opportunity and not vol_high and not atr_high:
        return "OBS_FAVORABLE"
    if obs_index >= thresholds["watch"] and (
        trend >= thresholds["trend_watch"] or momentum >= thresholds["momentum_watch"]
    ):
        return "WATCH"
    if vol_low and atr_low and weak_opportunity:
        return "LOW_RISK_WEAK"
    if obs_index < thresholds["weak"]:
        return "WEAK"
    return "WATCH"


def _asset_read(
    *,
    klass: str,
    trend: float,
    momentum: float,
    vol_high: bool,
    atr_high: bool,
    thresholds: dict[str, float],
) -> str:
    if klass == "MOM_HIGH_RISK":
        if trend >= thresholds["trend_strong"] and momentum >= thresholds["momentum_strong"]:
            return "strong trend/mom, risk high"
        return "momentum with risk"
    if klass == "OBS_FAVORABLE":
        return "relative observation only"
    if klass == "WATCH":
        if momentum >= thresholds["momentum_strong"]:
            return "momentum watch"
        if trend >= thresholds["trend_strong"]:
            return "trend watch"
        return "selective watch"
    if klass == "LOW_RISK_WEAK":
        return "low risk but weak"
    if klass == "DANGER":
        return "weak with extreme risk"
    if vol_high or atr_high:
        return "weak and risky"
    return "no momentum"


def _candidate_reason(row: dict[str, Any], thresholds: dict[str, float]) -> str:
    reasons: list[str] = []
    if row["trend"] >= thresholds["trend_strong"] and row["momentum"] >= thresholds["momentum_strong"]:
        reasons.append("strong trend/mom")
    elif row["momentum"] >= thresholds["momentum_strong"]:
        reasons.append("strong momentum")
    elif row["trend"] >= thresholds["trend_strong"]:
        reasons.append("strong trend")
    elif row["trend"] < thresholds["trend_watch"] and row["momentum"] < thresholds["momentum_watch"]:
        reasons.append("weak trend/mom")
    if row["vol_high"]:
        reasons.append("vol high")
    if row["atr_high"]:
        reasons.append("ATR high")
    return ", ".join(reasons) or row["read"]


def _observation_rows(
    assets: list[AssetSnapshot],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    vol_norm = _normalize_risk_values([asset.volatility_pct for asset in assets])
    atr_norm = _normalize_risk_values([asset.atr_pct for asset in assets])
    weights = _weights(config)
    thresholds = _thresholds(config)
    rows: list[dict[str, Any]] = []

    for asset, normalized_vol, normalized_atr in zip(assets, vol_norm, atr_norm, strict=True):
        trend = _clamp(asset.trend_score)
        momentum = _clamp(asset.momentum_score)
        volatility_safety = 100.0 - normalized_vol
        atr_safety = 100.0 - normalized_atr
        vol_high = normalized_vol >= thresholds["vol_high"]
        atr_high = normalized_atr >= thresholds["atr_high"]
        vol_extreme = normalized_vol >= thresholds["vol_extreme"]
        atr_extreme = normalized_atr >= thresholds["atr_extreme"]
        vol_low = normalized_vol < thresholds["vol_low"]
        atr_low = normalized_atr < thresholds["atr_low"]

        obs_index = (
            weights["trend"] * trend
            + weights["momentum"] * momentum
            + weights["volatility_safety"] * volatility_safety
            + weights["atr_safety"] * atr_safety
        )
        if vol_high:
            obs_index -= _risk_penalty(config, "vol_high")
        if atr_high:
            obs_index -= _risk_penalty(config, "atr_high")
        obs_index = _clamp(obs_index)

        klass = _asset_class(
            obs_index=obs_index,
            trend=trend,
            momentum=momentum,
            vol_high=vol_high,
            atr_high=atr_high,
            vol_extreme=vol_extreme,
            atr_extreme=atr_extreme,
            vol_low=vol_low,
            atr_low=atr_low,
            thresholds=thresholds,
        )
        row = {
            "ticker": asset.ticker,
            "sector": asset.sector,
            "obs_index": round(obs_index, 2),
            "class": klass,
            "trend": round(trend, 2),
            "momentum": round(momentum, 2),
            "volatility": round(asset.volatility_pct, 2),
            "atr": round(asset.atr_pct, 2),
            "normalized_volatility": round(normalized_vol, 2),
            "normalized_atr": round(normalized_atr, 2),
            "volatility_safety": round(volatility_safety, 2),
            "atr_safety": round(atr_safety, 2),
            "vol_high": vol_high,
            "atr_high": atr_high,
            "vol_extreme": vol_extreme,
            "atr_extreme": atr_extreme,
            "read": "",
        }
        row["read"] = _asset_read(
            klass=klass,
            trend=trend,
            momentum=momentum,
            vol_high=vol_high,
            atr_high=atr_high,
            thresholds=thresholds,
        )
        row["reason"] = _candidate_reason(row, thresholds)
        rows.append(row)

    return sorted(
        rows,
        key=lambda item: (
            -float(item["obs_index"]),
            OBS_CLASS_PRIORITY.get(str(item["class"]), 99),
            str(item["ticker"]),
        ),
    )


def _sector_class(rows: list[dict[str, Any]], avg_obs: float) -> tuple[str, str]:
    classes = {str(row["class"]) for row in rows}
    if "MOM_HIGH_RISK" in classes or "DANGER" in classes:
        return "VOLATILE", "best relative, high risk" if avg_obs >= 55 else "high risk"
    if "OBS_FAVORABLE" in classes:
        return "OBS_FAVORABLE", "relative strength"
    if avg_obs >= 55:
        return "MIXED", "selective"
    if avg_obs < 45:
        return "WEAK", "no momentum"
    return "MIXED", "selective"


def _sector_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["sector"]), []).append(row)

    summaries: list[dict[str, Any]] = []
    for sector, items in grouped.items():
        avg_obs = sum(float(item["obs_index"]) for item in items) / len(items)
        klass, read = _sector_class(items, avg_obs)
        summaries.append(
            {
                "sector": sector,
                "avg_obs": round(avg_obs, 2),
                "best_class": klass,
                "read": read,
            }
        )
    return sorted(summaries, key=lambda item: (-float(item["avg_obs"]), str(item["sector"])))


def run_observation(
    *,
    universe: str | Path = "data/universes/ibov_live.csv",
    list_name: str = "IBOV",
    config_path: str | Path = "config/observation.json",
    limit: int | None = None,
    cluster: bool = False,
) -> dict[str, Any]:
    config = load_observation_config(config_path)
    assets = load_universe_csv(universe)
    rows = _observation_rows(assets, config) if config.get("enabled", True) else []
    max_candidates = int(config.get("max_candidates", 10) or 10)
    limit_value = max_candidates if limit is None else max(1, int(limit))
    candidates = rows[:limit_value]

    return {
        "command": "observe",
        "list": str(list_name).upper(),
        "universe": str(universe),
        "enabled": bool(config.get("enabled", True)),
        "observation_type": "ranking_only",
        "not_trade_signal": True,
        "rows": rows,
        "candidates": candidates,
        "sector_summary": _sector_summary(rows)
        if bool(config.get("sector_summary", True))
        else [],
        "config": {
            "weights": config.get("weights", {}),
            "risk_penalty": config.get("risk_penalty", {}),
            "thresholds": _thresholds(config),
            "show_when_no_actionable": bool(config.get("show_when_no_actionable", True)),
            "max_candidates": max_candidates,
            "sector_summary": bool(config.get("sector_summary", True)),
            "unsupervised": config.get("unsupervised", {}),
        },
        "cluster": {
            "requested": bool(cluster),
            "enabled": bool(config.get("unsupervised", {}).get("enabled", False)) and bool(cluster),
            "method": config.get("unsupervised", {}).get("method", "kmeans"),
        },
    }


def observation_from_decisions(
    decisions: tuple[AssetDecision, ...] | list[AssetDecision],
    *,
    config_path: str | Path = "config/observation.json",
    limit: int | None = None,
) -> dict[str, Any]:
    config = load_observation_config(config_path)
    assets = [decision.asset for decision in decisions]
    rows = _observation_rows(assets, config) if config.get("enabled", True) else []
    max_candidates = int(config.get("max_candidates", 10) or 10)
    limit_value = max_candidates if limit is None else max(1, int(limit))
    return {
        "enabled": bool(config.get("enabled", True)),
        "show_when_no_actionable": bool(config.get("show_when_no_actionable", True)),
        "rows": rows,
        "candidates": rows[:limit_value],
        "sector_summary": _sector_summary(rows)
        if bool(config.get("sector_summary", True))
        else [],
        "config": {
            "max_candidates": max_candidates,
            "weights": config.get("weights", {}),
            "risk_penalty": config.get("risk_penalty", {}),
            "thresholds": _thresholds(config),
            "unsupervised": config.get("unsupervised", {}),
        },
    }


def _rounded_quantile(values: list[float], q: float, fallback: float) -> float:
    if not values:
        return fallback
    return round(_quantile(values, q), 2)


def calibrate_observation_thresholds(
    *,
    universe: str | Path = "data/universes/ibov_live.csv",
    list_name: str = "IBOV",
    config_path: str | Path = "config/observation.json",
    output: str | Path | None = None,
) -> dict[str, Any]:
    config = load_observation_config(config_path)
    assets = load_universe_csv(universe)
    rows = _observation_rows(assets, config) if config.get("enabled", True) else []
    defaults = _thresholds(config)
    obs_values = [float(row["obs_index"]) for row in rows]
    trend_values = [float(row["trend"]) for row in rows]
    momentum_values = [float(row["momentum"]) for row in rows]
    vol_values = [float(row["normalized_volatility"]) for row in rows]
    atr_values = [float(row["normalized_atr"]) for row in rows]

    thresholds = {
        "obs_ready": max(60.0, _rounded_quantile(obs_values, 0.75, defaults["obs_ready"])),
        "watch": max(45.0, _rounded_quantile(obs_values, 0.50, defaults["watch"])),
        "weak": min(50.0, _rounded_quantile(obs_values, 0.25, defaults["weak"])),
        "trend_strong": max(55.0, _rounded_quantile(trend_values, 0.60, defaults["trend_strong"])),
        "momentum_strong": max(55.0, _rounded_quantile(momentum_values, 0.60, defaults["momentum_strong"])),
        "trend_watch": max(45.0, _rounded_quantile(trend_values, 0.40, defaults["trend_watch"])),
        "momentum_watch": max(45.0, _rounded_quantile(momentum_values, 0.40, defaults["momentum_watch"])),
        "vol_high": max(50.0, _rounded_quantile(vol_values, 0.75, defaults["vol_high"])),
        "atr_high": max(60.0, _rounded_quantile(atr_values, 0.75, defaults["atr_high"])),
        "vol_extreme": max(75.0, _rounded_quantile(vol_values, 0.90, defaults["vol_extreme"])),
        "atr_extreme": max(75.0, _rounded_quantile(atr_values, 0.90, defaults["atr_extreme"])),
        "vol_low": min(45.0, _rounded_quantile(vol_values, 0.25, defaults["vol_low"])),
        "atr_low": min(45.0, _rounded_quantile(atr_values, 0.25, defaults["atr_low"])),
    }

    payload = {
        "command": "observe_calibrate",
        "schema_version": "observation_calibration.v1",
        "list": str(list_name).upper(),
        "universe": str(universe),
        "asset_count": len(rows),
        "calibration_type": "historical_universe_percentiles",
        "thresholds": thresholds,
        "config_patch": {"thresholds": thresholds},
        "notes": (
            "OBS_INDEX remains an observation ranking only; "
            "calibration does not create buy or short execution signals."
        ),
    }
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload["output"] = str(output_path)
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return payload


def render_observation_report(payload: dict[str, Any], *, limit: int | None = None) -> str:
    rows = payload.get("rows", [])
    if not isinstance(rows, list):
        rows = []
    limit_value = len(rows) if limit is None else max(1, int(limit))
    visible = rows[:limit_value]

    lines = [
        "OBSERVATION INDEX",
        muted_line(),
        f"{'#':>2} {'TICKER':<8} {'SECTOR':<12} {'OBS':>6} "
        f"{'CLASS':<14} {'TREND':>6} {'MOM':>6} {'VOL':>6} {'ATR':>6} READ",
    ]
    for index, row in enumerate(visible, start=1):
        lines.append(
            f"{index:>2} {row['ticker']:<8} {short_sector(row['sector'], 12):<12} "
            f"{float(row['obs_index']):>6.1f} {row['class']:<14} "
            f"{float(row['trend']):>6.1f} {float(row['momentum']):>6.1f} "
            f"{float(row['volatility']):>6.1f} {float(row['atr']):>6.2f} "
            f"{truncate(row['read'], 30)}"
        )

    sector_rows = payload.get("sector_summary", [])
    if isinstance(sector_rows, list) and sector_rows:
        lines.extend(
            [
                "",
                "SECTOR OBSERVATION",
                muted_line(),
                f"{'SECTOR':<18} {'AVG_OBS':>7} {'BEST_CLASS':<14} READ",
            ]
        )
        for row in sector_rows:
            lines.append(
                f"{short_sector(row['sector'], 18):<18} "
                f"{float(row['avg_obs']):>7.1f} {row['best_class']:<14} "
                f"{truncate(row['read'], 32)}"
            )

    return "\n".join(lines)


def render_observation_candidates(candidates: list[dict[str, Any]]) -> list[str]:
    if not candidates:
        return []
    lines = [
        "NO ACTIONABLE ASSETS",
        "",
        "OBSERVATION CANDIDATES",
        muted_line(),
        f"{'#':>2} {'TICKER':<8} {'OBS':>6} {'CLASS':<14} REASON",
    ]
    for index, row in enumerate(candidates, start=1):
        lines.append(
            f"{index:>2} {row['ticker']:<8} {float(row['obs_index']):>6.1f} "
            f"{row['class']:<14} {truncate(row['reason'], 48)}"
        )
    return lines
