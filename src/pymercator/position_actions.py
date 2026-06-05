from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pymercator.borrow_data import borrow_status_for_record, load_borrow_data, load_borrow_policy
from pymercator.domain import AssetDecision, DailyReport, ExecutionStatus, MarketRegime
from pymercator.explain import decision_codes
from pymercator.position_actions_config import load_position_actions_config
from pymercator.short_policy import (
    apply_legacy_short_overrides,
    load_short_policy,
    load_short_thresholds,
)
from pymercator.terminal_render import muted_line

DEFAULT_POSITIONS_PATH = "storage/positions/current_positions.csv"
POSITION_COLUMNS = ("ticker", "side", "qty", "avg_price", "entry_date")
OPTIONAL_POSITION_COLUMNS = ("stop", "trade_mode")
DEFAULT_BUY_TRADE_MODE = "SWING"
DEFAULT_EXIT_TRADE_MODE = "POSITION"
DEFAULT_SHORT_TRADE_MODE = "SWING"
VALID_TRADE_MODES = {"DAY_TRADE", "SWING", "POSITION"}


@dataclass(frozen=True)
class Position:
    ticker: str
    side: str
    qty: float
    avg_price: float
    entry_date: str
    stop: float | None = None
    trade_mode: str = DEFAULT_EXIT_TRADE_MODE


def _ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _direction(value: Any, *, default: str = "FLAT") -> str:
    text = str(value or "").strip().upper()
    return text if text in {"LONG", "SHORT", "FLAT"} else default


def _trade_mode(value: Any, *, default: str = DEFAULT_BUY_TRADE_MODE) -> str:
    text = str(value or "").strip().upper()
    return text if text in VALID_TRADE_MODES else default


def load_positions(
    path: str | Path = DEFAULT_POSITIONS_PATH,
    *,
    require_exists: bool = False,
) -> list[Position]:
    source = Path(path)
    if not source.exists():
        if require_exists:
            raise FileNotFoundError(f"positions file not found: {source}")
        return []

    with source.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        columns = set(reader.fieldnames or [])
        missing = [column for column in POSITION_COLUMNS if column not in columns]
        if missing:
            raise ValueError(f"positions file missing columns: {', '.join(missing)}")

        positions: list[Position] = []
        for row in reader:
            ticker = _ticker(row.get("ticker"))
            side = str(row.get("side") or "LONG").strip().upper()
            qty = _to_float(row.get("qty"))
            avg_price = _to_float(row.get("avg_price"))
            if not ticker or qty <= 0 or avg_price <= 0:
                continue
            positions.append(
                Position(
                    ticker=ticker,
                    side=side,
                    qty=qty,
                    avg_price=avg_price,
                    entry_date=str(row.get("entry_date") or "").strip(),
                    stop=(
                        _to_float(row.get("stop"))
                        if str(row.get("stop") or "").strip()
                        else None
                    ),
                    trade_mode=_trade_mode(
                        row.get("trade_mode"),
                        default=DEFAULT_EXIT_TRADE_MODE,
                    ),
                )
            )
    return positions


def write_positions(
    positions: list[Position],
    path: str | Path = DEFAULT_POSITIONS_PATH,
) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=POSITION_COLUMNS)
        writer.writeheader()
        for position in positions:
            writer.writerow(
                {
                    "ticker": position.ticker,
                    "side": position.side,
                    "qty": position.qty,
                    "avg_price": position.avg_price,
                    "entry_date": position.entry_date,
                }
            )


def import_positions_file(
    source: str | Path,
    *,
    output: str | Path = DEFAULT_POSITIONS_PATH,
) -> dict[str, Any]:
    positions = load_positions(source, require_exists=True)
    output_path = Path(output)
    if Path(source).resolve() == output_path.resolve():
        return {
            "status": "OK",
            "source": str(source),
            "output": str(output_path),
            "positions": len(positions),
        }
    write_positions(positions, output_path)
    return {
        "status": "OK",
        "source": str(source),
        "output": str(output_path),
        "positions": len(positions),
    }


def positions_to_dicts(positions: list[Position]) -> list[dict[str, Any]]:
    return [asdict(position) for position in positions]


def _prediction_quality(prediction: dict[str, Any] | None) -> str:
    quality = (prediction or {}).get("model_quality", {})
    if isinstance(quality, dict):
        return str(quality.get("status") or "").upper()
    return ""


def _prediction_behavior(prediction: dict[str, Any] | None) -> str:
    return str((prediction or {}).get("behavior") or "").upper()


def _combined_score(prediction: dict[str, Any] | None) -> float:
    return _to_float((prediction or {}).get("combined_score"), 50.0)


def _is_risk_off(report: DailyReport) -> bool:
    return report.market_regime.regime == MarketRegime.RISK_OFF


def _decision_map(report: DailyReport) -> dict[str, AssetDecision]:
    return {_ticker(decision.asset.ticker): decision for decision in report.decisions}


def _long_reason(decision: AssetDecision) -> str:
    codes = [code for code in decision_codes(decision) if code not in {"OK", "CAUTION"}]
    if codes:
        return "+".join(codes[:4])
    if decision.permission.status == ExecutionStatus.READY:
        return "buy setup allowed"
    if decision.permission.status == ExecutionStatus.WATCH:
        return "watch only"
    return "blocked"


def build_long_book(report: DailyReport, *, limit: int = 10) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for decision in sorted(
        report.decisions,
        key=lambda item: item.ranking.context_score,
        reverse=True,
    )[: max(1, int(limit))]:
        status = decision.permission.status
        if status == ExecutionStatus.READY:
            action = "BUY_READY"
        elif status == ExecutionStatus.WATCH:
            action = "WATCH"
        else:
            action = "BLOCKED"
        rows.append(
            {
                "ticker": decision.asset.ticker,
                "direction": "LONG",
                "trade_mode": DEFAULT_BUY_TRADE_MODE,
                "action": action,
                "score": round(float(decision.ranking.context_score), 2),
                "reason": _long_reason(decision),
            }
        )
    return rows


def _pnl_pct(position: Position, current_price: float) -> float:
    if position.avg_price <= 0:
        return 0.0
    if position.side == "SHORT":
        return ((position.avg_price - current_price) / position.avg_price) * 100.0
    return ((current_price - position.avg_price) / position.avg_price) * 100.0


def _risk_flags(decision: AssetDecision, config: dict[str, Any]) -> tuple[bool, bool]:
    asset = decision.asset
    exit_config = config.get("exit", {}) if isinstance(config, dict) else {}
    vol_limit = _to_float(exit_config.get("vol_high_pct"), 8.0)
    atr_limit = _to_float(exit_config.get("atr_high_pct"), 6.0)
    vol_high = asset.volatility_pct >= vol_limit or not decision.validation.volatility_ok
    atr_high = asset.atr_pct >= atr_limit or not decision.validation.atr_ok
    return vol_high, atr_high


def _exit_row(
    position: Position,
    decision: AssetDecision | None,
    report: DailyReport,
    prediction: dict[str, Any] | None,
    config: dict[str, Any],
) -> dict[str, Any]:
    exit_config = config.get("exit", {}) if isinstance(config, dict) else {}
    manual_review = config.get("manual_review", {}) if isinstance(config, dict) else {}
    if decision is None:
        return {
            "ticker": position.ticker,
            "direction": _direction(position.side),
            "trade_mode": _trade_mode(position.trade_mode, default=DEFAULT_EXIT_TRADE_MODE),
            "action": "HOLD",
            "pnl_pct": None,
            "risk": "UNKNOWN",
            "manual_review_required": bool(
                manual_review.get("position_outside_universe", True)
            ),
            "reason": "position outside current universe",
        }

    asset = decision.asset
    current_price = float(asset.last_close)
    pnl = _pnl_pct(position, current_price)
    stop = position.stop or decision.validation.stop or asset.stop
    if position.side == "SHORT":
        stop_hit = bool(stop is not None and current_price >= float(stop))
    else:
        stop_hit = bool(stop is not None and current_price <= float(stop))
    vol_high, atr_high = _risk_flags(decision, config)
    take_profit_pct = _to_float(exit_config.get("take_profit_pct"), 8.0)
    stop_loss_pct = _to_float(exit_config.get("stop_loss_pct"), -3.0)
    trail_profit_pct = _to_float(exit_config.get("trail_profit_pct"), 5.0)
    profit_relevant = pnl >= take_profit_pct
    deteriorating = asset.trend_score < 55.0 or asset.momentum_score < 55.0
    defensive = (
        (bool(exit_config.get("risk_off_reduce", True)) and _is_risk_off(report))
        or (
            bool(exit_config.get("model_weak_reduce", True))
            and _prediction_quality(prediction) in {"WEAK", "DEGENERATE"}
        )
        or (
            bool(exit_config.get("behavior_avoid_reduce", True))
            and _prediction_behavior(prediction) == "AVOID"
        )
    )

    if stop_hit:
        return {
            "ticker": position.ticker,
            "direction": _direction(position.side),
            "trade_mode": _trade_mode(position.trade_mode, default=DEFAULT_EXIT_TRADE_MODE),
            "action": "STOP_LOSS",
            "pnl_pct": round(pnl, 2),
            "risk": "STOP",
            "severity": "HIGH",
            "manual_review_required": False,
            "reason": "stop reached",
        }
    if pnl <= stop_loss_pct:
        return {
            "ticker": position.ticker,
            "direction": _direction(position.side),
            "trade_mode": _trade_mode(position.trade_mode, default=DEFAULT_EXIT_TRADE_MODE),
            "action": "STOP_LOSS",
            "pnl_pct": round(pnl, 2),
            "risk": "STOP",
            "severity": "HIGH",
            "manual_review_required": False,
            "reason": "loss threshold",
        }
    if profit_relevant and deteriorating:
        return {
            "ticker": position.ticker,
            "direction": _direction(position.side),
            "trade_mode": _trade_mode(position.trade_mode, default=DEFAULT_EXIT_TRADE_MODE),
            "action": "TAKE_PROFIT",
            "pnl_pct": round(pnl, 2),
            "risk": "OK" if not (vol_high or atr_high) else "HIGH",
            "manual_review_required": False,
            "reason": "profit with trend/mom deterioration",
        }
    if pnl >= trail_profit_pct and (vol_high or atr_high):
        return {
            "ticker": position.ticker,
            "direction": _direction(position.side),
            "trade_mode": _trade_mode(position.trade_mode, default=DEFAULT_EXIT_TRADE_MODE),
            "action": "TRAIL_STOP",
            "pnl_pct": round(pnl, 2),
            "risk": "HIGH",
            "manual_review_required": False,
            "reason": "profit with rising volatility",
        }
    if defensive and vol_high and atr_high:
        return {
            "ticker": position.ticker,
            "direction": _direction(position.side),
            "trade_mode": _trade_mode(position.trade_mode, default=DEFAULT_EXIT_TRADE_MODE),
            "action": "EXIT_FULL",
            "pnl_pct": round(pnl, 2),
            "risk": "HIGH",
            "severity": "HIGH",
            "manual_review_required": False,
            "reason": "structural risk breach",
        }
    if defensive:
        return {
            "ticker": position.ticker,
            "direction": _direction(position.side),
            "trade_mode": _trade_mode(position.trade_mode, default=DEFAULT_EXIT_TRADE_MODE),
            "action": "REDUCE",
            "pnl_pct": round(pnl, 2),
            "risk": "HIGH" if (vol_high or atr_high) else "CAUTION",
            "manual_review_required": False,
            "reason": "defensive regime/model/behavior",
        }
    if asset.trend_score >= 55.0 and asset.momentum_score >= 50.0 and not (vol_high or atr_high):
        return {
            "ticker": position.ticker,
            "direction": _direction(position.side),
            "trade_mode": _trade_mode(position.trade_mode, default=DEFAULT_EXIT_TRADE_MODE),
            "action": "HOLD",
            "pnl_pct": round(pnl, 2),
            "risk": "OK",
            "manual_review_required": False,
            "reason": "trend still valid",
        }
    return {
        "ticker": position.ticker,
        "direction": _direction(position.side),
        "trade_mode": _trade_mode(position.trade_mode, default=DEFAULT_EXIT_TRADE_MODE),
        "action": "REDUCE",
        "pnl_pct": round(pnl, 2),
        "risk": "HIGH" if (vol_high or atr_high) else "CAUTION",
        "manual_review_required": False,
        "reason": "trend/momentum deteriorating",
    }


def build_exit_book(
    report: DailyReport,
    positions: list[Position],
    prediction: dict[str, Any] | None = None,
    *,
    positions_file: str | Path = DEFAULT_POSITIONS_PATH,
    loaded: bool = False,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decisions = _decision_map(report)
    resolved_config = config or load_position_actions_config()
    if not positions:
        return {
            "positions_loaded": loaded,
            "positions_file": str(positions_file),
            "rows": [],
            "message": "no open positions loaded.",
        }
    rows = [
        _exit_row(
            position,
            decisions.get(_ticker(position.ticker)),
            report,
            prediction,
            resolved_config,
        )
        for position in positions
    ]
    return {
        "positions_loaded": loaded,
        "positions_file": str(positions_file),
        "rows": rows,
        "message": "",
    }


def _sector_weakness(report: DailyReport) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}
    for decision in report.decisions:
        opportunity = (decision.asset.trend_score + decision.asset.momentum_score) / 2.0
        grouped.setdefault(decision.asset.sector, []).append(_clamp(opportunity))
    return {
        sector: 100.0 - (sum(values) / len(values))
        for sector, values in grouped.items()
        if values
    }


def _short_runtime_config(
    config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    policy = load_short_policy()
    thresholds = load_short_thresholds()
    return apply_legacy_short_overrides(
        policy=policy,
        thresholds=thresholds,
        position_actions_config=config,
    )


def _short_score(
    decision: AssetDecision,
    report: DailyReport,
    prediction: dict[str, Any] | None,
    sector_weakness: dict[str, float],
    thresholds: dict[str, Any],
) -> float:
    asset = decision.asset
    weak_trend = 100.0 - _clamp(asset.trend_score)
    weak_momentum = 100.0 - _clamp(asset.momentum_score)
    model_bearish = 100.0 - _clamp(_combined_score(prediction))
    regime_pressure = 100.0 if _is_risk_off(report) else 0.0
    if _prediction_quality(prediction) in {"WEAK", "DEGENERATE"}:
        model_bearish = max(model_bearish, 70.0)
    if _prediction_behavior(prediction) == "AVOID":
        model_bearish = max(model_bearish, 75.0)

    score = (
        0.30 * weak_trend
        + 0.30 * weak_momentum
        + 0.20 * model_bearish
        + 0.10 * regime_pressure
        + 0.10 * sector_weakness.get(asset.sector, 0.0)
    )
    risk = thresholds.get("risk", {}) if isinstance(thresholds, dict) else {}
    max_volatility = _to_float(risk.get("max_volatility"), 55.0)
    max_atr = _to_float(risk.get("max_atr"), 6.0)
    if asset.volatility_pct >= max_volatility:
        score -= 15.0
    if asset.atr_pct >= max_atr:
        score -= 15.0
    if asset.liquidity_score < 40.0:
        score -= 20.0
    return _clamp(score)


def _short_setup_status(
    decision: AssetDecision,
    score: float,
    report: DailyReport,
    prediction: dict[str, Any] | None,
    thresholds: dict[str, Any],
) -> tuple[str, str]:
    asset = decision.asset
    setup = thresholds.get("setup", {}) if isinstance(thresholds, dict) else {}
    min_score = _to_float(setup.get("min_short_score"), 70.0)
    max_trend = _to_float(setup.get("max_trend"), 40.0)
    max_momentum = _to_float(setup.get("max_momentum"), 40.0)
    weak_asset = asset.trend_score <= max_trend and asset.momentum_score <= max_momentum
    defensive_market = (
        _is_risk_off(report)
        or _prediction_quality(prediction) in {"WEAK", "DEGENERATE"}
        or _prediction_behavior(prediction) == "AVOID"
    )
    if weak_asset and score >= min_score:
        return "SHORT_SETUP", "weak trend and momentum"
    if defensive_market and score >= max(0.0, min_score - 10.0):
        return "WEAK_SHORT_SETUP", "defensive hedge candidate"
    return "NO_SHORT_SETUP", "short setup not present"


def _short_risk_status(
    decision: AssetDecision,
    thresholds: dict[str, Any],
) -> tuple[str, str]:
    asset = decision.asset
    risk = thresholds.get("risk", {}) if isinstance(thresholds, dict) else {}
    max_volatility = _to_float(risk.get("max_volatility"), 55.0)
    max_atr = _to_float(risk.get("max_atr"), 6.0)
    vol_high = asset.volatility_pct >= max_volatility
    atr_high = asset.atr_pct >= max_atr
    low_liquidity = asset.liquidity_score < 40.0
    if low_liquidity or (vol_high and atr_high):
        return "RISK_BLOCK", "short technical risk blocked"
    if vol_high or atr_high:
        return "RISK_CAUTION", "short technical risk caution"
    return "RISK_OK", "technical risk ok"


def _event_status() -> tuple[str, str]:
    return "EVENT_UNKNOWN", "event calendar unavailable"


def _ready_long_count(report: DailyReport) -> int:
    return sum(
        1
        for decision in report.decisions
        if decision.permission.status == ExecutionStatus.READY
    )


def _market_read(
    report: DailyReport,
    prediction: dict[str, Any] | None,
    sector_scores: dict[str, float] | None = None,
) -> str:
    parts: list[str] = []
    if _is_risk_off(report):
        parts.append("risk-off")

    if report.decisions:
        avg_trend = sum(
            float(decision.asset.trend_score) for decision in report.decisions
        ) / len(report.decisions)
        if avg_trend < 45.0 or _is_risk_off(report):
            parts.append("downtrend")

    if _prediction_quality(prediction) in {"WEAK", "DEGENERATE"}:
        parts.append("weak model")
    if _prediction_behavior(prediction) == "AVOID":
        parts.append("behavior avoid")

    scores = sector_scores or _sector_weakness(report)
    if scores and (sum(scores.values()) / len(scores)) >= 55.0:
        parts.append("broad weakness")

    if not parts:
        parts.append("no actionable long assets")
    return " / ".join(dict.fromkeys(parts))


def _hedge_reason(
    report: DailyReport,
    prediction: dict[str, Any] | None,
    sector_scores: dict[str, float],
) -> str:
    reasons: list[str] = []
    if _is_risk_off(report):
        reasons.append("risk-off")
    if sector_scores and (sum(sector_scores.values()) / len(sector_scores)) >= 50.0:
        reasons.append("broad weakness")
    if _prediction_quality(prediction) in {"WEAK", "DEGENERATE"}:
        reasons.append("weak model")
    if _prediction_behavior(prediction) == "AVOID":
        reasons.append("behavior avoid")
    return " + ".join(reasons) if reasons else "long basket blocked"


def _build_hedge_candidates(
    report: DailyReport,
    prediction: dict[str, Any] | None,
    *,
    active: bool,
    long_actionable: int,
    sector_scores: dict[str, float],
) -> list[dict[str, Any]]:
    if not active:
        return []

    rows: list[dict[str, Any]] = []
    pressure = (
        _is_risk_off(report)
        or _prediction_quality(prediction) in {"WEAK", "DEGENERATE"}
        or _prediction_behavior(prediction) == "AVOID"
    )
    if pressure:
        rows.append(
            {
                "target": "INDEX",
                "action": "HEDGE_WATCH",
                "reason": _hedge_reason(report, prediction, sector_scores),
            }
        )

    weak_sectors = sorted(
        sector_scores.items(),
        key=lambda item: (-float(item[1]), str(item[0])),
    )
    for sector, weakness in weak_sectors[:2]:
        if weakness < 50.0:
            continue
        rows.append(
            {
                "target": "SECTOR",
                "action": "HEDGE_WATCH",
                "reason": f"{sector} weak",
            }
        )

    if long_actionable == 0:
        rows.append(
            {
                "target": "CASH",
                "action": "HOLD_CASH",
                "reason": "no long basket allowed",
            }
        )

    return rows


def build_defensive_book(
    report: DailyReport,
    prediction: dict[str, Any] | None,
    *,
    short_candidates: list[dict[str, Any]],
    sector_scores: dict[str, float] | None = None,
) -> dict[str, Any]:
    long_actionable = _ready_long_count(report)
    sector_scores = sector_scores or _sector_weakness(report)
    pressure = (
        _is_risk_off(report)
        or _prediction_quality(prediction) in {"WEAK", "DEGENERATE"}
        or _prediction_behavior(prediction) == "AVOID"
    )
    active = long_actionable == 0 or pressure
    hedge_candidates = _build_hedge_candidates(
        report,
        prediction,
        active=active,
        long_actionable=long_actionable,
        sector_scores=sector_scores,
    )
    cash_reason = (
        "no executable defensive trade"
        if active
        else "defensive mode inactive"
    )
    if active and not hedge_candidates and not short_candidates:
        cash_reason = "no short or hedge setup available"

    return {
        "status": "ACTIVE" if active else "INACTIVE",
        "market_read": _market_read(report, prediction, sector_scores),
        "long_action": "blocked" if long_actionable == 0 else "allowed",
        "long_actionable": long_actionable,
        "defensive_mode": "active" if active else "inactive",
        "short_candidates": list(short_candidates),
        "hedge_candidates": hedge_candidates,
        "cash_wait_mode": {
            "action": "HOLD_CASH" if active else "NO_SHIFT",
            "reason": cash_reason,
        },
    }


def _short_permission(
    *,
    setup_status: str,
    risk_status: str,
    borrow_status: str,
    event_status: str,
    policy: dict[str, Any],
    thresholds: dict[str, Any],
) -> tuple[str, str]:
    if setup_status == "NO_SHORT_SETUP":
        return "DATA_MISSING", "short setup not present"
    if risk_status == "RISK_BLOCK":
        return "SHORT_BLOCKED", "short risk blocked"

    borrow_thresholds = thresholds.get("borrow", {}) if isinstance(thresholds, dict) else {}
    if bool(policy.get("requires_borrow_data", True)):
        if borrow_status in {
            "BORROW_DATA_MISSING",
            "BORROW_STALE",
            "BORROW_UNAVAILABLE",
            "BORROW_COST_HIGH",
            "BORROW_RECALL_RISK",
            "BORROW_LIQUIDITY_WEAK",
        }:
            return "SHORT_BLOCKED", borrow_status.lower()
        if borrow_status == "BORROW_SQUEEZE_HIGH":
            if bool(borrow_thresholds.get("manual_if_squeeze_risk_high", True)):
                return "SHORT_MANUAL_ONLY", "squeeze risk high"
            return "SHORT_BLOCKED", "squeeze risk high"

    if event_status == "EVENT_BLOCK":
        return "SHORT_BLOCKED", "event blocked"
    if str(policy.get("mode", "MANUAL_ONLY")).upper() == "MANUAL_ONLY":
        return "SHORT_MANUAL_ONLY", "policy manual only"
    if not bool(policy.get("allow_execution", False)):
        return "SHORT_MANUAL_ONLY", "short execution disabled"
    if borrow_status == "BORROW_OK" and risk_status in {"RISK_OK", "RISK_CAUTION"}:
        return "SHORT_READY", "short checks passed"
    return "SHORT_BLOCKED", "short checks incomplete"


def _short_row(
    decision: AssetDecision,
    report: DailyReport,
    prediction: dict[str, Any] | None,
    sector_scores: dict[str, float],
    policy: dict[str, Any],
    thresholds: dict[str, Any],
    borrow_policy: dict[str, Any],
    borrow_record: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not bool(policy.get("enabled", True)):
        return None
    score = _short_score(decision, report, prediction, sector_scores, thresholds)
    setup_status, setup_reason = _short_setup_status(
        decision,
        score,
        report,
        prediction,
        thresholds,
    )
    if setup_status == "NO_SHORT_SETUP":
        return None
    risk_status, risk_reason = _short_risk_status(decision, thresholds)
    borrow_status, borrow_reason = borrow_status_for_record(
        borrow_record,
        thresholds=thresholds,
        policy=borrow_policy,
    )
    event_status, event_reason = _event_status()
    permission, permission_reason = _short_permission(
        setup_status=setup_status,
        risk_status=risk_status,
        borrow_status=borrow_status,
        event_status=event_status,
        policy=policy,
        thresholds=thresholds,
    )
    reason = permission_reason
    if permission == "SHORT_BLOCKED" and borrow_status != "BORROW_OK":
        reason = borrow_reason
    elif permission == "SHORT_MANUAL_ONLY" and borrow_status == "BORROW_OK":
        reason = permission_reason

    row = {
        "ticker": decision.asset.ticker,
        "bias": "SHORT",
        "direction": "SHORT",
        "trade_mode": str(policy.get("allowed_trade_modes", ["SWING"])[0] or "SWING"),
        "short_score": round(score, 2),
        "score": round(score, 2),
        "class": setup_status,
        "executable": False,
        "short_setup_status": setup_status,
        "short_risk_status": risk_status,
        "borrow_status": borrow_status,
        "event_status": event_status,
        "short_permission": permission,
        "permission": permission,
        "action": permission,
        "borrow_available": None if not borrow_record else borrow_record.get("borrow_available"),
        "borrow_fee_pct": None if not borrow_record else borrow_record.get("borrow_fee_pct"),
        "recall_risk": "UNKNOWN" if not borrow_record else borrow_record.get("recall_risk", "UNKNOWN"),
        "short_liquidity": "UNKNOWN" if not borrow_record else borrow_record.get("short_liquidity", "UNKNOWN"),
        "squeeze_risk": "UNKNOWN" if not borrow_record else borrow_record.get("squeeze_risk", "UNKNOWN"),
        "manual_only": permission == "SHORT_MANUAL_ONLY",
        "observational_only": True,
        "execution": "OBSERVATIONAL_ONLY",
        "reason": reason,
        "setup_reason": setup_reason,
        "risk_reason": risk_reason,
        "borrow_reason": borrow_reason,
        "event_reason": event_reason,
    }
    if borrow_record:
        row["borrow"] = dict(borrow_record)
    return row


def short_observation_candidates(short_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in short_candidates:
        rows.append(
            {
                "ticker": row.get("ticker", "-"),
                "bias": "SHORT",
                "score": row.get("short_score", row.get("score", 0.0)),
                "class": row.get("short_setup_status", "SHORT_SETUP"),
                "reason": row.get("setup_reason") or row.get("reason", "-"),
                "executable": False,
                "borrow_status": row.get("borrow_status", "-"),
                "permission": row.get("short_permission", row.get("permission", "-")),
            }
        )
    return rows


def build_short_book(
    report: DailyReport,
    positions: list[Position],
    prediction: dict[str, Any] | None = None,
    *,
    limit: int = 10,
    config: dict[str, Any] | None = None,
    borrow_records: dict[str, dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    resolved_config = config or load_position_actions_config()
    borrow_records = borrow_records or {}
    policy, thresholds = _short_runtime_config(resolved_config)
    borrow_policy = load_borrow_policy()
    positioned = {_ticker(position.ticker) for position in positions if position.side == "LONG"}
    sector_scores = _sector_weakness(report)
    rows: list[dict[str, Any]] = []
    for decision in report.decisions:
        if _ticker(decision.asset.ticker) in positioned:
            continue
        ticker = _ticker(decision.asset.ticker)
        row = _short_row(
            decision,
            report,
            prediction,
            sector_scores,
            policy,
            thresholds,
            borrow_policy,
            borrow_records.get(ticker),
        )
        if not row:
            continue
        rows.append(row)

    rows = sorted(rows, key=lambda item: (-float(item["score"]), str(item["ticker"])))
    rows = rows[: max(1, int(limit))]
    return {
        "rows": rows,
        "short_candidates": [
            row for row in rows if row.get("short_setup_status") == "SHORT_SETUP"
        ],
        "hedge_candidates": [
            row for row in rows if row.get("short_setup_status") == "WEAK_SHORT_SETUP"
        ],
    }


def build_position_actions(
    report: DailyReport,
    prediction: dict[str, Any] | None = None,
    *,
    positions_path: str | Path = DEFAULT_POSITIONS_PATH,
    long_limit: int = 10,
    short_limit: int = 10,
    config_path: str | Path = "config/position_actions.json",
    borrow_data_path: str | Path | None = None,
) -> dict[str, Any]:
    config = load_position_actions_config(config_path)
    short_config = config.get("short", {}) if isinstance(config, dict) else {}
    short_policy, short_thresholds = _short_runtime_config(config)
    resolved_borrow_path = (
        borrow_data_path
        if borrow_data_path is not None
        else short_config.get("borrow_data_path", "")
    )
    borrow_status, borrow_records = load_borrow_data(resolved_borrow_path)
    source = Path(positions_path)
    positions = load_positions(source)
    loaded = source.exists() and len(positions) > 0
    exit_book = build_exit_book(
        report,
        positions,
        prediction,
        positions_file=source,
        loaded=loaded,
        config=config,
    )
    short_book = build_short_book(
        report,
        positions,
        prediction,
        limit=short_limit,
        config=config,
        borrow_records=borrow_records,
    )
    short_observation = short_observation_candidates(short_book["short_candidates"])
    sector_scores = _sector_weakness(report)
    defensive_book = build_defensive_book(
        report,
        prediction,
        short_candidates=short_book["short_candidates"],
        sector_scores=sector_scores,
    )
    return {
        "schema_version": "position_actions.v1",
        "config": {
            "schema_version": config.get("schema_version"),
            "source": config.get("config_source", str(config_path)),
            "status": config.get("config_status", "UNKNOWN"),
            "warning": config.get("config_warning", ""),
        },
        "positions_file": str(source),
        "positions_loaded": loaded,
        "positions": positions_to_dicts(positions),
        "borrow_data": borrow_status,
        "short_policy": {
            "schema_version": short_policy.get("schema_version"),
            "mode": short_policy.get("mode", "MANUAL_ONLY"),
            "allow_execution": bool(short_policy.get("allow_execution", False)),
            "never_enter_long_basket": bool(short_policy.get("never_enter_long_basket", True)),
        },
        "short_thresholds": {
            "schema_version": short_thresholds.get("schema_version"),
            "setup": short_thresholds.get("setup", {}),
            "risk": short_thresholds.get("risk", {}),
            "borrow": short_thresholds.get("borrow", {}),
            "events": short_thresholds.get("events", {}),
        },
        "long_book": build_long_book(report, limit=long_limit),
        "exit_book": exit_book,
        "defensive_book": defensive_book,
        "short_book": short_book["rows"],
        "short_candidates": short_book["short_candidates"],
        "short_observation_candidates": short_observation,
        "hedge_candidates": defensive_book["hedge_candidates"],
        "equity_hedge_candidates": short_book["hedge_candidates"],
        "short_execution": "OBSERVATIONAL_ONLY",
    }


def render_positions(positions: list[Position], *, source: str | Path) -> str:
    lines = [
        "POSITIONS",
        muted_line(),
        f"source {source}",
        "",
        f"{'TICKER':<8} {'SIDE':<6} {'QTY':>10} {'AVG_PRICE':>10} ENTRY_DATE",
    ]
    if not positions:
        lines.append("no open positions loaded.")
        return "\n".join(lines)
    for position in positions:
        lines.append(
            f"{position.ticker:<8} {position.side:<6} "
            f"{position.qty:>10.0f} {position.avg_price:>10.2f} "
            f"{position.entry_date}"
        )
    return "\n".join(lines)


def render_position_books(position_actions: dict[str, Any]) -> list[str]:
    from pymercator.short_render import render_position_books as renderer

    return renderer(position_actions)


def position_actions_to_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
