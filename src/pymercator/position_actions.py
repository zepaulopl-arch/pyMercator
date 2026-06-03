from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pymercator.domain import AssetDecision, DailyReport, ExecutionStatus, MarketRegime
from pymercator.explain import decision_codes
from pymercator.ui import muted_line, truncate

DEFAULT_POSITIONS_PATH = "storage/positions/current_positions.csv"
POSITION_COLUMNS = ("ticker", "side", "qty", "avg_price", "entry_date")


@dataclass(frozen=True)
class Position:
    ticker: str
    side: str
    qty: float
    avg_price: float
    entry_date: str


def _ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


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
            writer.writerow(asdict(position))


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


def _risk_flags(decision: AssetDecision) -> tuple[bool, bool]:
    asset = decision.asset
    vol_high = asset.volatility_pct >= 8.0 or not decision.validation.volatility_ok
    atr_high = asset.atr_pct >= 6.0 or not decision.validation.atr_ok
    return vol_high, atr_high


def _exit_row(
    position: Position,
    decision: AssetDecision | None,
    report: DailyReport,
    prediction: dict[str, Any] | None,
) -> dict[str, Any]:
    if decision is None:
        return {
            "ticker": position.ticker,
            "action": "HOLD",
            "pnl_pct": 0.0,
            "risk": "UNKNOWN",
            "reason": "position not in current universe",
        }

    asset = decision.asset
    current_price = float(asset.last_close)
    pnl = _pnl_pct(position, current_price)
    stop = decision.validation.stop or asset.stop
    stop_hit = bool(stop is not None and current_price <= float(stop))
    vol_high, atr_high = _risk_flags(decision)
    profit_relevant = pnl >= 8.0
    deteriorating = asset.trend_score < 55.0 or asset.momentum_score < 55.0
    defensive = (
        _is_risk_off(report)
        or _prediction_quality(prediction) in {"WEAK", "DEGENERATE"}
        or _prediction_behavior(prediction) == "AVOID"
    )

    if stop_hit:
        return {
            "ticker": position.ticker,
            "action": "EXIT_FULL",
            "pnl_pct": round(pnl, 2),
            "risk": "STOP",
            "reason": "stop reached",
        }
    if profit_relevant and deteriorating:
        return {
            "ticker": position.ticker,
            "action": "TAKE_PROFIT",
            "pnl_pct": round(pnl, 2),
            "risk": "OK" if not (vol_high or atr_high) else "HIGH",
            "reason": "profit with trend/mom deterioration",
        }
    if profit_relevant and (vol_high or atr_high):
        return {
            "ticker": position.ticker,
            "action": "TRAIL_STOP",
            "pnl_pct": round(pnl, 2),
            "risk": "HIGH",
            "reason": "profit with rising volatility",
        }
    if defensive:
        return {
            "ticker": position.ticker,
            "action": "REDUCE",
            "pnl_pct": round(pnl, 2),
            "risk": "HIGH" if (vol_high or atr_high) else "CAUTION",
            "reason": "defensive regime/model/behavior",
        }
    if asset.trend_score >= 55.0 and asset.momentum_score >= 50.0 and not (vol_high or atr_high):
        return {
            "ticker": position.ticker,
            "action": "HOLD",
            "pnl_pct": round(pnl, 2),
            "risk": "OK",
            "reason": "trend still valid",
        }
    return {
        "ticker": position.ticker,
        "action": "REDUCE",
        "pnl_pct": round(pnl, 2),
        "risk": "HIGH" if (vol_high or atr_high) else "CAUTION",
        "reason": "trend/momentum deteriorating",
    }


def build_exit_book(
    report: DailyReport,
    positions: list[Position],
    prediction: dict[str, Any] | None = None,
    *,
    positions_file: str | Path = DEFAULT_POSITIONS_PATH,
    loaded: bool = False,
) -> dict[str, Any]:
    decisions = _decision_map(report)
    if not positions:
        return {
            "positions_loaded": loaded,
            "positions_file": str(positions_file),
            "rows": [],
            "message": "no open positions loaded.",
        }
    rows = [
        _exit_row(position, decisions.get(_ticker(position.ticker)), report, prediction)
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
    if asset.volatility_pct >= 15.0:
        score -= 15.0
    if asset.atr_pct >= 10.0:
        score -= 15.0
    if asset.liquidity_score < 40.0:
        score -= 20.0
    return _clamp(score)


def _short_action(
    decision: AssetDecision,
    score: float,
    report: DailyReport,
    prediction: dict[str, Any] | None,
) -> tuple[str, str]:
    asset = decision.asset
    weak_asset = asset.trend_score < 45.0 and asset.momentum_score < 45.0
    extreme_risk = asset.volatility_pct >= 15.0 or asset.atr_pct >= 10.0
    low_liquidity = asset.liquidity_score < 40.0
    defensive_market = (
        _is_risk_off(report)
        or _prediction_quality(prediction) in {"WEAK", "DEGENERATE"}
        or _prediction_behavior(prediction) == "AVOID"
    )

    if weak_asset and (extreme_risk or low_liquidity):
        return "SHORT_BLOCKED", "weak asset but short risk unavailable"
    if weak_asset and score >= 60.0:
        return "SHORT_CANDIDATE", "weak trend + weak mom + risk off"
    if defensive_market and score >= 55.0:
        return "HEDGE_CANDIDATE", "defensive hedge candidate"
    return "", ""


def build_short_book(
    report: DailyReport,
    positions: list[Position],
    prediction: dict[str, Any] | None = None,
    *,
    limit: int = 10,
) -> dict[str, list[dict[str, Any]]]:
    positioned = {_ticker(position.ticker) for position in positions if position.side == "LONG"}
    sector_scores = _sector_weakness(report)
    rows: list[dict[str, Any]] = []
    for decision in report.decisions:
        if _ticker(decision.asset.ticker) in positioned:
            continue
        score = _short_score(decision, report, prediction, sector_scores)
        action, reason = _short_action(decision, score, report, prediction)
        if not action:
            continue
        rows.append(
            {
                "ticker": decision.asset.ticker,
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
) -> dict[str, Any]:
    source = Path(positions_path)
    positions = load_positions(source)
    loaded = source.exists() and len(positions) > 0
    exit_book = build_exit_book(
        report,
        positions,
        prediction,
        positions_file=source,
        loaded=loaded,
    )
    short_book = build_short_book(
        report,
        positions,
        prediction,
        limit=short_limit,
    )
    return {
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
        "LONG BOOK",
        muted_line(),
        f"{'#':>2} {'TICKER':<8} {'ACTION':<10} {'SCORE':>7} REASON",
    ]
    long_rows = position_actions.get("long_book", [])
    if not isinstance(long_rows, list) or not long_rows:
        lines.append("no long book rows.")
    else:
        for index, row in enumerate(long_rows, start=1):
            lines.append(
                f"{index:>2} {row['ticker']:<8} {row['action']:<10} "
                f"{float(row['score']):>7.2f} {truncate(row['reason'], 48)}"
            )

    exit_book = position_actions.get("exit_book", {})
    exit_rows = exit_book.get("rows", []) if isinstance(exit_book, dict) else []
    lines.extend(
        [
            "",
            "EXIT BOOK",
            muted_line(),
            f"{'#':>2} {'TICKER':<8} {'ACTION':<12} {'PNL%':>7} {'RISK':<7} REASON",
        ]
    )
    if not exit_rows:
        message = "no open positions loaded."
        if isinstance(exit_book, dict):
            message = str(exit_book.get("message") or message)
        lines.append(message)
    else:
        for index, row in enumerate(exit_rows, start=1):
            pnl = float(row.get("pnl_pct", 0.0))
            lines.append(
                f"{index:>2} {row['ticker']:<8} {row['action']:<12} "
                f"{pnl:>+7.1f} {row['risk']:<7} {truncate(row['reason'], 44)}"
            )

    short_rows = position_actions.get("short_book", [])
    lines.extend(
        [
            "",
            "SHORT / HEDGE BOOK",
            muted_line(),
            f"{'#':>2} {'TICKER':<8} {'ACTION':<16} {'SCORE':>7} REASON",
        ]
    )
    if not isinstance(short_rows, list) or not short_rows:
        lines.append("no short or hedge candidates.")
    else:
        for index, row in enumerate(short_rows, start=1):
            lines.append(
                f"{index:>2} {row['ticker']:<8} {row['action']:<16} "
                f"{float(row['score']):>7.1f} {truncate(row['reason'], 44)}"
            )
    return lines


def position_actions_to_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
