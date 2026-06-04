from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pymercator.domain import AssetDecision, DailyReport, ExecutionStatus, MarketRegime
from pymercator.explain import decision_codes
from pymercator.position_actions_config import load_position_actions_config
from pymercator.ui import muted_line, truncate

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


def _short_score(
    decision: AssetDecision,
    report: DailyReport,
    prediction: dict[str, Any] | None,
    sector_weakness: dict[str, float],
    config: dict[str, Any],
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
    short_config = config.get("short", {}) if isinstance(config, dict) else {}
    max_volatility = _to_float(short_config.get("max_volatility"), 60.0)
    max_atr = _to_float(short_config.get("max_atr"), 7.0)
    if asset.volatility_pct >= max_volatility:
        score -= 15.0
    if asset.atr_pct >= max_atr:
        score -= 15.0
    if asset.liquidity_score < 40.0:
        score -= 20.0
    return _clamp(score)


def _short_action(
    decision: AssetDecision,
    score: float,
    report: DailyReport,
    prediction: dict[str, Any] | None,
    config: dict[str, Any],
) -> tuple[str, str]:
    asset = decision.asset
    short_config = config.get("short", {}) if isinstance(config, dict) else {}
    hedge_config = config.get("hedge", {}) if isinstance(config, dict) else {}
    if not bool(short_config.get("enabled", True)) and not bool(hedge_config.get("enabled", True)):
        return "", ""
    min_short_score = _to_float(short_config.get("min_short_score"), 65.0)
    max_volatility = _to_float(short_config.get("max_volatility"), 60.0)
    max_atr = _to_float(short_config.get("max_atr"), 7.0)
    weak_asset = asset.trend_score < 45.0 and asset.momentum_score < 45.0
    extreme_risk = asset.volatility_pct >= max_volatility or asset.atr_pct >= max_atr
    low_liquidity = asset.liquidity_score < 40.0
    defensive_market = (
        _is_risk_off(report)
        or _prediction_quality(prediction) in {"WEAK", "DEGENERATE"}
        or _prediction_behavior(prediction) == "AVOID"
    )

    short_enabled = bool(short_config.get("enabled", True))
    if short_enabled and weak_asset and (extreme_risk or low_liquidity):
        return "SHORT_BLOCKED", "weak asset but short risk unavailable"
    if short_enabled and weak_asset and score >= min_short_score:
        if (
            bool(short_config.get("requires_borrow_data", True))
            and bool(short_config.get("block_without_borrow_data", True))
        ):
            return "SHORT_BLOCKED", "borrow/cost data unavailable"
        return "SHORT_CANDIDATE", "weak trend + weak mom + risk off"
    if (
        bool(hedge_config.get("enabled", True))
        and bool(hedge_config.get("risk_off_hedge_candidate", True))
        and defensive_market
        and score >= max(0.0, min_short_score - 10.0)
    ):
        return "HEDGE_CANDIDATE", "defensive hedge candidate"
    return "", ""


def build_short_book(
    report: DailyReport,
    positions: list[Position],
    prediction: dict[str, Any] | None = None,
    *,
    limit: int = 10,
    config: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    resolved_config = config or load_position_actions_config()
    positioned = {_ticker(position.ticker) for position in positions if position.side == "LONG"}
    sector_scores = _sector_weakness(report)
    rows: list[dict[str, Any]] = []
    for decision in report.decisions:
        if _ticker(decision.asset.ticker) in positioned:
            continue
        score = _short_score(decision, report, prediction, sector_scores, resolved_config)
        action, reason = _short_action(decision, score, report, prediction, resolved_config)
        if not action:
            continue
        rows.append(
            {
                "ticker": decision.asset.ticker,
                "direction": "SHORT",
                "trade_mode": DEFAULT_SHORT_TRADE_MODE,
                "action": action,
                "score": round(score, 2),
                "reason": reason,
                "execution": "OBSERVATIONAL_ONLY",
            }
        )

    rows = sorted(rows, key=lambda item: (-float(item["score"]), str(item["ticker"])))
    rows = rows[: max(1, int(limit))]
    return {
        "rows": rows,
        "short_candidates": [
            row for row in rows if row["action"] == "SHORT_CANDIDATE"
        ],
        "hedge_candidates": [
            row for row in rows if row["action"] == "HEDGE_CANDIDATE"
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
) -> dict[str, Any]:
    config = load_position_actions_config(config_path)
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
        "long_book": build_long_book(report, limit=long_limit),
        "exit_book": exit_book,
        "short_book": short_book["rows"],
        "short_candidates": short_book["short_candidates"],
        "hedge_candidates": short_book["hedge_candidates"],
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
    if not position_actions:
        return []

    lines = [
        "BUY / LONG BOOK",
        muted_line(),
        "direction         LONG",
        "meaning           bought/long position; benefits from price rising",
        f"mode              {DEFAULT_BUY_TRADE_MODE}",
        "",
        (
            f"{'#':>2} {'TICKER':<8} {'DIR':<5} {'MODE':<10} "
            f"{'ACTION':<10} {'SCORE':>7} REASON"
        ),
    ]
    long_rows = position_actions.get("long_book", [])
    if not isinstance(long_rows, list) or not long_rows:
        lines.append("no long book rows.")
    else:
        for index, row in enumerate(long_rows, start=1):
            lines.append(
                f"{index:>2} {row['ticker']:<8} "
                f"{str(row.get('direction', 'LONG')):<5} "
                f"{str(row.get('trade_mode', DEFAULT_BUY_TRADE_MODE)):<10} "
                f"{row['action']:<10} "
                f"{float(row['score']):>7.2f} {truncate(row['reason'], 48)}"
            )

    exit_book = position_actions.get("exit_book", {})
    exit_rows = exit_book.get("rows", []) if isinstance(exit_book, dict) else []
    lines.extend(
        [
            "",
            "EXIT BOOK",
            muted_line(),
            (
                f"{'#':>2} {'TICKER':<8} {'DIR':<5} {'MODE':<10} {'ACTION':<12} {'PNL%':>7} "
                f"{'RISK':<7} {'REVIEW':<6} REASON"
            ),
        ]
    )
    if not exit_rows:
        message = "no open positions loaded."
        if isinstance(exit_book, dict):
            message = str(exit_book.get("message") or message)
        lines.append(message)
    else:
        for index, row in enumerate(exit_rows, start=1):
            pnl_value = row.get("pnl_pct")
            pnl = "n/a" if pnl_value is None else f"{float(pnl_value):+7.1f}"
            review = "YES" if row.get("manual_review_required") else "NO"
            lines.append(
                f"{index:>2} {row['ticker']:<8} "
                f"{str(row.get('direction', 'LONG')):<5} "
                f"{str(row.get('trade_mode', DEFAULT_EXIT_TRADE_MODE)):<10} "
                f"{row['action']:<12} "
                f"{pnl:>7} {row['risk']:<7} {review:<6} {truncate(row['reason'], 44)}"
            )

    short_rows = position_actions.get("short_book", [])
    lines.extend(
        [
            "",
            "SELL-SHORT / HEDGE BOOK",
            muted_line(),
            "direction         SHORT",
            "meaning           sold/borrowed position; benefits from price falling",
            f"mode              {DEFAULT_SHORT_TRADE_MODE}",
            "requires          borrow availability, borrow cost and short risk checks",
            "",
            (
                f"{'#':>2} {'TICKER':<8} {'DIR':<5} {'MODE':<10} "
                f"{'ACTION':<16} {'SCORE':>7} REASON"
            ),
        ]
    )
    if not isinstance(short_rows, list) or not short_rows:
        lines.append("no short or hedge candidates.")
    else:
        for index, row in enumerate(short_rows, start=1):
            lines.append(
                f"{index:>2} {row['ticker']:<8} "
                f"{str(row.get('direction', 'SHORT')):<5} "
                f"{str(row.get('trade_mode', DEFAULT_SHORT_TRADE_MODE)):<10} "
                f"{row['action']:<16} "
                f"{float(row['score']):>7.1f} {truncate(row['reason'], 44)}"
            )
    return lines


def position_actions_to_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
