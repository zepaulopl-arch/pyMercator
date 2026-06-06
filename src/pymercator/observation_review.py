from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pymercator.data.prices_csv import read_price_rows_csv

REVIEW_COLUMNS = [
    "section",
    "ticker",
    "direction",
    "obs_class",
    "signal",
    "execution",
    "score",
    "main_reason",
    "ref_price",
    "ref_date",
    "ref_ts",
    "ref_source",
    "review_price",
    "review_date",
    "review_ts",
    "review_source",
    "price_status",
    "reference_date",
    "reference_price",
    "current_date",
    "current_price",
    "return_pct",
    "notional",
    "pnl_long",
    "pnl_short",
    "pnl",
    "sim_pnl",
    "real_pnl",
    "review_status",
    "review_class",
    "hypothetical",
]


@dataclass(frozen=True)
class PricePoint:
    date: str
    close: float


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_text(value: Any, default: str = "-") -> str:
    text = "" if value is None else str(value).strip()
    return text or default


def _normalize_ticker(ticker: Any) -> str:
    return _as_text(ticker, "").upper().replace(".SA", "")


def _normalize_execution(value: Any) -> str:
    text = _as_text(value).upper()
    if "DATA_MISSING" in text or "BORROW_DATA_MISSING" in text:
        return "DATA_BLOCKED"
    if "SHORT_BLOCKED" in text or "BLOCKED" in text:
        return "BLOCKED"
    if "MANUAL" in text:
        return "WATCH"
    if text in {"OK", "ALLOW", "READY", "SHORT_READY"}:
        return "READY"
    if text in {"-", ""}:
        return "WATCH"
    return text


def _price_file(prices_dir: str | Path, ticker: str) -> Path:
    base = Path(prices_dir)
    clean = _normalize_ticker(ticker)
    candidates = [
        base / f"{clean}.SA.csv",
        base / f"{clean}.csv",
        base / f"{clean.lower()}.SA.csv",
        base / f"{clean.lower()}.csv",
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def _read_price_points(prices_dir: str | Path, ticker: str) -> list[PricePoint]:
    path = _price_file(prices_dir, ticker)
    rows = read_price_rows_csv(path)
    points: list[PricePoint] = []
    for row in rows:
        date = _as_text(row.get("date"), "")
        close = _as_float(row.get("close"), default=0.0)
        if date and close > 0:
            points.append(PricePoint(date=date, close=close))
    return sorted(points, key=lambda item: item.date)


def _parse_signal_date(run_dir: Path) -> str:
    name = run_dir.name
    parts = name.split("_")
    for part in parts:
        if len(part) == 8 and part.isdigit():
            return f"{part[0:4]}-{part[4:6]}-{part[6:8]}"
    return datetime.now().date().isoformat()


def _reference_point(
    *,
    points: list[PricePoint],
    fallback_price: float | None,
    signal_date: str,
    ref_date: str = "",
) -> PricePoint | None:
    if fallback_price and fallback_price > 0:
        return PricePoint(date=ref_date or signal_date, close=fallback_price)

    before_signal = [point for point in points if point.date <= signal_date]
    if before_signal:
        return before_signal[-1]
    if points:
        return points[0]
    return None


def _current_point(points: list[PricePoint]) -> PricePoint | None:
    return points[-1] if points else None


def _decision_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in payload.get("decisions", []) or []:
        asset = item.get("asset", {}) if isinstance(item, dict) else {}
        ticker = _normalize_ticker(asset.get("ticker") or item.get("ticker"))
        if ticker:
            result[ticker] = item
    return result


def _decision_ticker(item: dict[str, Any]) -> str:
    asset = item.get("asset", {}) if isinstance(item.get("asset"), dict) else {}
    return _normalize_ticker(asset.get("ticker") or item.get("ticker"))


def _decision_score(item: dict[str, Any]) -> float:
    ranking = item.get("ranking", {}) if isinstance(item.get("ranking"), dict) else {}
    return _as_float(ranking.get("context_score") or ranking.get("raw_score"))


def _decision_reference_price(item: dict[str, Any]) -> float | None:
    value = _as_float(item.get("ref_price"), default=0.0)
    return value if value > 0 else None


def _decision_reference_fields(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref_price": _decision_reference_price(item),
        "ref_date": _as_text(item.get("ref_date"), ""),
        "ref_ts": _as_text(item.get("ref_ts"), ""),
        "ref_source": _as_text(item.get("ref_source"), ""),
    }


def _item_reference_fields(
    item: dict[str, Any],
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fallback = fallback or {}
    price = _as_float(item.get("ref_price"), default=0.0)
    if price <= 0:
        price = _as_float(fallback.get("ref_price"), default=0.0)
    return {
        "ref_price": price if price > 0 else None,
        "ref_date": _as_text(item.get("ref_date") or fallback.get("ref_date"), ""),
        "ref_ts": _as_text(item.get("ref_ts") or fallback.get("ref_ts"), ""),
        "ref_source": _as_text(
            item.get("ref_source") or fallback.get("ref_source"), ""
        ),
    }


def _decision_reason(item: dict[str, Any]) -> str:
    reasons = item.get("blocker_reasons")
    if isinstance(reasons, list) and reasons:
        return "+".join(_as_text(reason) for reason in reasons)
    return _as_text(item.get("decision_label"))


def _decision_execution(item: dict[str, Any]) -> str:
    permission = (
        item.get("permission", {}) if isinstance(item.get("permission"), dict) else {}
    )
    validation = (
        item.get("validation", {}) if isinstance(item.get("validation"), dict) else {}
    )
    return _normalize_execution(permission.get("status") or validation.get("status"))


def _long_signal(item: dict[str, Any]) -> str:
    ranking = item.get("ranking", {}) if isinstance(item.get("ranking"), dict) else {}
    raw = _as_text(ranking.get("context_signal") or ranking.get("raw_signal"), "BUY")
    return "BUY_SETUP" if raw.upper() in {"BUY", "LONG"} else "NO_SETUP"


def _short_execution(item: dict[str, Any]) -> str:
    borrow = _as_text(item.get("borrow_status")).upper()
    if "MISSING" in borrow or "UNKNOWN" in borrow:
        return "DATA_BLOCKED"
    return _normalize_execution(item.get("short_permission") or item.get("permission"))


def _short_reason(item: dict[str, Any], execution: str) -> str:
    if execution == "DATA_BLOCKED":
        return "borrow data missing"
    return _as_text(
        item.get("borrow_reason") or item.get("reason") or item.get("setup_reason")
    )


def _classify_block(direction: str, pnl: float, *, relevance_brl: float) -> str:
    if pnl > relevance_brl:
        return "MISSED_OPPORTUNITY"
    if pnl < -relevance_brl:
        return "GOOD_BLOCK"
    return "NEUTRAL_BLOCK"


def _classify_directional(prefix: str, pnl: float, *, relevance_brl: float) -> str:
    if pnl > relevance_brl:
        return f"{prefix}_GAIN"
    if pnl < -relevance_brl:
        return f"{prefix}_LOSS"
    return f"{prefix}_FLAT"


def _review_row(
    *,
    section: str,
    ticker: str,
    direction: str,
    obs_class: str,
    signal: str,
    execution: str,
    score: float,
    main_reason: str,
    ref_price: float | None,
    ref_date: str,
    ref_ts: str,
    ref_source: str,
    signal_date: str,
    prices_dir: str | Path,
    notional: float,
    hypothetical: bool,
    relevance_brl: float,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "section": section,
        "ticker": ticker,
        "direction": direction,
        "obs_class": obs_class,
        "signal": signal,
        "execution": execution,
        "score": round(score, 2),
        "main_reason": main_reason,
        "ref_price": ref_price,
        "ref_date": ref_date or "-",
        "ref_ts": ref_ts or "-",
        "ref_source": ref_source or "-",
        "review_price": None,
        "review_date": "-",
        "review_ts": "-",
        "review_source": "-",
        "price_status": "DATA_MISSING",
        "reference_date": "-",
        "reference_price": None,
        "current_date": "-",
        "current_price": None,
        "return_pct": None,
        "notional": round(notional, 2),
        "pnl_long": None,
        "pnl_short": None,
        "pnl": None,
        "sim_pnl": None,
        "real_pnl": 0.0,
        "review_status": "NOT_REVIEWED",
        "review_class": "-",
        "hypothetical": hypothetical,
    }

    if not ref_price or ref_price <= 0:
        row["review_class"] = "DATA_MISSING"
        row["main_reason"] = (
            "Cannot compute MTM: missing reference prices from signal time."
        )
        return row

    try:
        review_source = str(_price_file(prices_dir, ticker))
        points = _read_price_points(prices_dir, ticker)
    except Exception as exc:
        row["price_status"] = "DATA_MISSING"
        row["review_class"] = "DATA_MISSING"
        row["main_reason"] = f"review price data missing: {exc}"
        return row

    ref = _reference_point(
        points=points,
        fallback_price=ref_price,
        signal_date=signal_date,
        ref_date=ref_date,
    )
    current = _current_point(points)
    if ref is None or current is None:
        row["price_status"] = "DATA_MISSING"
        row["review_class"] = "DATA_MISSING"
        row["main_reason"] = "reference or review price data missing"
        return row

    row.update(
        {
            "reference_date": ref.date,
            "reference_price": round(ref.close, 4),
            "current_date": current.date,
            "current_price": round(current.close, 4),
            "review_date": current.date,
            "review_price": round(current.close, 4),
            "review_ts": datetime.now().isoformat(timespec="seconds"),
            "review_source": review_source,
        }
    )

    if current.date < ref.date:
        row["price_status"] = "STALE"
        row["review_class"] = "STALE"
        row["main_reason"] = "review price is older than reference price"
        return row

    return_pct = ((current.close / ref.close) - 1.0) * 100.0
    pnl_long = notional * (return_pct / 100.0)
    pnl_short = -pnl_long
    pnl = pnl_long if direction == "LONG" else pnl_short
    real_pnl = pnl if execution == "READY" and not hypothetical else 0.0

    row.update(
        {
            "reference_date": ref.date,
            "reference_price": round(ref.close, 4),
            "current_date": current.date,
            "current_price": round(current.close, 4),
            "return_pct": round(return_pct, 4),
            "pnl_long": round(pnl_long, 2),
            "pnl_short": round(pnl_short, 2),
            "pnl": round(pnl, 2),
            "sim_pnl": round(pnl, 2),
            "real_pnl": round(real_pnl, 2),
            "price_status": "OK",
            "review_status": "REVIEWED",
        }
    )
    if section in {"long_observation", "short_observation"}:
        row["review_class"] = _classify_directional(
            "HYPOTHETICAL",
            pnl,
            relevance_brl=relevance_brl,
        )
    elif execution == "READY":
        row["review_class"] = _classify_directional(
            "EXECUTABLE",
            pnl,
            relevance_brl=relevance_brl,
        )
    elif execution == "WATCH":
        row["review_class"] = _classify_directional(
            "WATCH",
            pnl,
            relevance_brl=relevance_brl,
        )
    elif execution in {"BLOCKED", "DATA_BLOCKED"}:
        row["review_class"] = _classify_block(
            direction,
            pnl,
            relevance_brl=relevance_brl,
        )
    return row


def _allocate(capital: float, count: int) -> float:
    return capital / count if count > 0 else 0.0


def _short_candidate_source(payload: dict[str, Any]) -> list[dict[str, Any]]:
    short_candidates = payload.get("short_candidates", []) or []
    if short_candidates:
        return [item for item in short_candidates if isinstance(item, dict)]
    defensive = (
        payload.get("defensive_book", {})
        if isinstance(payload.get("defensive_book"), dict)
        else {}
    )
    return [
        item
        for item in defensive.get("short_candidates", []) or []
        if isinstance(item, dict)
    ]


def _build_raw_rows(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    decisions = payload.get("decisions", []) or []
    decision_by_ticker = _decision_index(payload)

    long_signals: list[dict[str, Any]] = []
    for item in decisions:
        if not isinstance(item, dict):
            continue
        ref = _decision_reference_fields(item)
        long_signals.append(
            {
                "ticker": _decision_ticker(item),
                "direction": "LONG",
                "obs_class": "SIGNAL",
                "signal": _long_signal(item),
                "execution": _decision_execution(item),
                "score": _decision_score(item),
                "main_reason": _decision_reason(item),
                **ref,
            }
        )

    short_signals: list[dict[str, Any]] = []
    for item in _short_candidate_source(payload):
        execution = _short_execution(item)
        ticker = _normalize_ticker(item.get("ticker"))
        ref = _item_reference_fields(
            item,
            _decision_reference_fields(decision_by_ticker.get(ticker, {})),
        )
        short_signals.append(
            {
                "ticker": ticker,
                "direction": "SHORT",
                "obs_class": _as_text(item.get("class"), "SHORT_SETUP"),
                "signal": "SELL_SETUP",
                "execution": execution,
                "score": _as_float(item.get("score") or item.get("short_score")),
                "main_reason": _short_reason(item, execution),
                **ref,
            }
        )

    long_observations: list[dict[str, Any]] = []
    for item in payload.get("observation_candidates", []) or []:
        ticker = _normalize_ticker(item.get("ticker"))
        decision = decision_by_ticker.get(ticker, {})
        ref = _item_reference_fields(item, _decision_reference_fields(decision))
        long_observations.append(
            {
                "ticker": ticker,
                "direction": "LONG",
                "obs_class": _as_text(item.get("class"), "WATCH").replace(
                    "OBS_READY", "OBS_FAVORABLE"
                ),
                "signal": _long_signal(decision) if decision else "BUY_SETUP",
                "execution": _decision_execution(decision) if decision else "WATCH",
                "score": _as_float(item.get("score") or item.get("obs_index")),
                "main_reason": (
                    _decision_reason(decision)
                    if decision
                    else _as_text(item.get("reason"))
                ),
                **ref,
            }
        )

    short_observation_source = payload.get("short_observation_candidates", []) or []
    if not short_observation_source:
        short_observation_source = _short_candidate_source(payload)

    short_observations: list[dict[str, Any]] = []
    for item in short_observation_source:
        if not isinstance(item, dict):
            continue
        execution = _short_execution(item)
        ticker = _normalize_ticker(item.get("ticker"))
        ref = _item_reference_fields(
            item,
            _decision_reference_fields(decision_by_ticker.get(ticker, {})),
        )
        short_observations.append(
            {
                "ticker": ticker,
                "direction": "SHORT",
                "obs_class": _as_text(item.get("class"), "SHORT_SETUP"),
                "signal": "SELL_SETUP",
                "execution": execution,
                "score": _as_float(item.get("score") or item.get("short_score")),
                "main_reason": _short_reason(item, execution),
                **ref,
            }
        )

    return {
        "long_signals": long_signals,
        "short_signals": short_signals,
        "long_observation": long_observations,
        "short_observation": short_observations,
    }


def _section_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in rows if row.get("review_status") == "REVIEWED"]
    wins = [row for row in valid if _as_float(row.get("sim_pnl")) > 0]
    total_pnl = sum(_as_float(row.get("sim_pnl")) for row in valid)
    real_pnl = sum(_as_float(row.get("real_pnl")) for row in valid)
    returns = [
        _as_float(row.get("return_pct"))
        for row in valid
        if row.get("return_pct") is not None
    ]
    long_rows = [row for row in valid if row.get("direction") == "LONG"]
    short_rows = [row for row in valid if row.get("direction") == "SHORT"]
    long_pnl = sum(_as_float(row.get("sim_pnl")) for row in long_rows)
    short_pnl = sum(_as_float(row.get("sim_pnl")) for row in short_rows)
    long_returns = [
        _as_float(row.get("return_pct"))
        for row in long_rows
        if row.get("return_pct") is not None
    ]
    short_returns = [
        _as_float(row.get("return_pct"))
        for row in short_rows
        if row.get("return_pct") is not None
    ]
    long_wins = [row for row in long_rows if _as_float(row.get("sim_pnl")) > 0]
    short_wins = [row for row in short_rows if _as_float(row.get("sim_pnl")) > 0]
    long_items = sum(1 for row in rows if row.get("direction") == "LONG")
    short_items = sum(1 for row in rows if row.get("direction") == "SHORT")
    ready_items = sum(1 for row in rows if row.get("execution") == "READY")
    watch_items = sum(1 for row in rows if row.get("execution") == "WATCH")
    blocked_items = sum(
        1 for row in rows if row.get("execution") in {"BLOCKED", "DATA_BLOCKED"}
    )
    missing_reference = sum(
        1
        for row in rows
        if row.get("price_status") == "DATA_MISSING"
        and "missing reference" in str(row.get("main_reason", "")).lower()
    )
    stale_items = sum(1 for row in rows if row.get("price_status") == "STALE")
    classes: dict[str, int] = {}
    for row in rows:
        klass = _as_text(row.get("review_class"))
        classes[klass] = classes.get(klass, 0) + 1
    best = max(valid, key=lambda row: _as_float(row.get("sim_pnl")), default=None)
    worst = min(valid, key=lambda row: _as_float(row.get("sim_pnl")), default=None)
    notional_values = [
        _as_float(row.get("notional"))
        for row in rows
        if row.get("notional") not in (None, "")
    ]
    notional_per_item = notional_values[0] if notional_values else 0.0

    def compact(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        return {
            "ticker": row.get("ticker"),
            "direction": row.get("direction"),
            "return_pct": row.get("return_pct"),
            "sim_pnl": row.get("sim_pnl"),
        }

    return {
        "items": len(rows),
        "valid_items": len(valid),
        "notional_per_item": round(notional_per_item, 2),
        "data_missing": sum(
            1 for row in rows if row.get("price_status") == "DATA_MISSING"
        ),
        "missing_reference": missing_reference,
        "stale_items": stale_items,
        "long_items": long_items,
        "short_items": short_items,
        "ready_items": ready_items,
        "watch_items": watch_items,
        "blocked_items": blocked_items,
        "hit_rate": round((len(wins) / len(valid)) * 100.0, 2) if valid else 0.0,
        "avg_return_pct": round(sum(returns) / len(returns), 4) if returns else 0.0,
        "pnl_total": round(total_pnl, 2),
        "sim_pnl": round(total_pnl, 2),
        "real_pnl": round(real_pnl, 2),
        "total_long_pnl": round(long_pnl, 2),
        "total_short_pnl": round(short_pnl, 2),
        "total_observation_pnl": round(total_pnl, 2),
        "long_hit_rate": (
            round((len(long_wins) / len(long_rows)) * 100.0, 2) if long_rows else 0.0
        ),
        "short_hit_rate": (
            round((len(short_wins) / len(short_rows)) * 100.0, 2) if short_rows else 0.0
        ),
        "avg_long_return": (
            round(sum(long_returns) / len(long_returns), 4) if long_returns else None
        ),
        "avg_short_return": (
            round(sum(short_returns) / len(short_returns), 4) if short_returns else None
        ),
        "best_observation": compact(best),
        "worst_observation": compact(worst),
        "classes": classes,
    }


def _render_money(value: Any) -> str:
    if value is None or value == "":
        return "NA"
    return f"{_as_float(value):,.2f}"


def _render_pct(value: Any) -> str:
    if value is None:
        return "NA"
    return f"{_as_float(value):.2f}%"


def _market_read(long_pnl: float, short_pnl: float) -> str:
    if long_pnl == short_pnl:
        return "MIXED"
    if long_pnl > 0 and short_pnl <= 0:
        return "LONG_BETTER_THAN_SHORT"
    if short_pnl > 0 and long_pnl <= 0:
        return "SHORT_BETTER_THAN_LONG"
    if long_pnl > 0 and short_pnl > 0:
        return "BOTH_POSITIVE"
    if long_pnl < 0 and short_pnl < 0:
        return "BOTH_NEGATIVE"
    if long_pnl > short_pnl:
        return "LONG_BETTER_THAN_SHORT"
    if short_pnl > long_pnl:
        return "SHORT_BETTER_THAN_LONG"
    return "MIXED"


def _compact_best_worst(summary: dict[str, Any]) -> tuple[str, str]:
    best = summary.get("best_observation") or {}
    worst = summary.get("worst_observation") or {}
    best_text = f"{best.get('ticker', '-')} {best.get('direction', '-')} R$ {_render_money(best.get('sim_pnl'))}"
    worst_text = f"{worst.get('ticker', '-')} {worst.get('direction', '-')} R$ {_render_money(worst.get('sim_pnl'))}"
    return best_text, worst_text


def _render_table_rows(
    title: str,
    rows: list[dict[str, Any]],
    limit: int = 12,
    radar_section: bool = False,
    status_label: str = "RADAR_STATUS",
) -> list[str]:
    def _row_status(row: dict[str, Any]) -> str:
        if radar_section:
            status = _as_text(row.get("review_class"), "-")
            if status in {"MISSED_OPPORTUNITY", "GOOD_BLOCK", "NEUTRAL_BLOCK"}:
                pnl = _as_float(row.get("sim_pnl"))
                if pnl > 0:
                    return "RADAR_GAIN"
                if pnl < 0:
                    return "RADAR_LOSS"
                return "RADAR_FLAT"
            return status
        return _as_text(row.get("execution"), "-")

    lines = [title, "-" * 80]
    lines.append(
        f"{'#':>2}  {'TICKER':<8} {'EXECUTION':<12} {'SCORE':>6} {'MOVE':>8} {'PNL':>11} {status_label:<12} REASON"
    )
    if not rows:
        lines.append("status             EMPTY")
        lines.append("reason             no items")
        return lines
    for index, row in enumerate(rows[:limit], start=1):
        lines.append(
            f"{index:>2}  {row['ticker']:<8} {row['execution']:<12} "
            f"{_as_float(row.get('score')):>6.1f} {_render_pct(row.get('return_pct')):>8} "
            f"{_render_money(row.get('sim_pnl')):>11} {_row_status(row):<12} {row['main_reason']}"
        )
    if len(rows) > limit:
        lines.append(f"... {len(rows) - limit} more rows in observation_review.csv")
    return lines


def _render_not_computed_review(payload: dict[str, Any]) -> str:
    outputs = (
        payload.get("outputs", {}) if isinstance(payload.get("outputs"), dict) else {}
    )
    reason = (
        payload.get("cannot_compute_reason")
        or payload.get("reason")
        or "Cannot compute MTM: missing reference prices from signal time."
    )
    lines = [
        "AURUM MTM REVIEW",
        "-" * 80,
        "status             NOT_COMPUTED",
        f"reason             {reason}",
        f"capital            R$ {_render_money(payload.get('capital'))}",
        f"run_dir            {payload.get('run_dir')}",
        "",
        "FINANCIAL RESULT",
        "-" * 80,
        "real_trades        0",
        "real_pnl           R$ 0.00",
        "observation_pnl    NOT COMPUTED",
        "long_pnl           NOT COMPUTED",
        "short_pnl          NOT COMPUTED",
        f"data_missing       {payload.get('data_missing', 0)}",
        "",
        "ACTION REQUIRED",
        "-" * 80,
        "Run a new daily signal after enabling reference price capture.",
    ]
    return "\n".join(lines)


def _render_real_operations(rows: list[dict[str, Any]]) -> list[str]:
    long_rows = [row for row in rows if row.get("direction") == "LONG"]
    short_rows = [row for row in rows if row.get("direction") == "SHORT"]
    real_long_pnl = round(sum(_as_float(row.get("real_pnl")) for row in long_rows), 2)
    real_short_pnl = round(sum(_as_float(row.get("real_pnl")) for row in short_rows), 2)
    real_total_pnl = round(real_long_pnl + real_short_pnl, 2)
    lines = ["REAL OPERATIONS", "-" * 80]
    if not rows:
        lines.extend(
            [
                "status             NO REAL TRADES",
                "real_long_items    0",
                "real_long_pnl      R$ 0.00",
                "real_short_items   0",
                "real_short_pnl     R$ 0.00",
                "real_total_pnl     R$ 0.00",
            ]
        )
        return lines

    lines.extend(
        [
            f"real_long_items    {len(long_rows)}",
            f"real_long_pnl      R$ {_render_money(real_long_pnl)}",
            f"real_short_items   {len(short_rows)}",
            f"real_short_pnl     R$ {_render_money(real_short_pnl)}",
            f"real_total_pnl     R$ {_render_money(real_total_pnl)}",
        ]
    )
    if long_rows:
        lines.append("")
        lines.extend(
            _render_table_rows(
                "REAL LONG",
                long_rows,
                limit=12,
                radar_section=False,
                status_label="STATUS",
            )
        )
    if short_rows:
        lines.append("")
        lines.extend(
            _render_table_rows(
                "REAL SHORT",
                short_rows,
                limit=12,
                radar_section=False,
                status_label="STATUS",
            )
        )
    return lines


def _render_radar_summary(
    long_rows: list[dict[str, Any]], short_rows: list[dict[str, Any]]
) -> list[str]:
    long_summary = _section_summary(long_rows)
    short_summary = _section_summary(short_rows)
    long_best, long_worst = _compact_best_worst(long_summary)
    short_best, short_worst = _compact_best_worst(short_summary)
    radar_total_items = len(long_rows) + len(short_rows)
    radar_total_pnl = round(long_summary["pnl_total"] + short_summary["pnl_total"], 2)
    market_read = _market_read(long_summary["pnl_total"], short_summary["pnl_total"])
    verdict = (
        "RADAR_GAIN"
        if radar_total_pnl > 0
        else "RADAR_LOSS" if radar_total_pnl < 0 else "FLAT"
    )

    lines = ["RADAR SUMMARY", "-" * 80]
    lines.extend(
        [
            f"radar_long_items   {long_summary['items']}",
            f"radar_long_pnl     R$ {_render_money(long_summary['pnl_total'])}",
            f"radar_long_hit     {_render_pct(long_summary['hit_rate'])}",
            f"radar_long_avg_move {_render_pct(long_summary['avg_return_pct'])}",
            f"best_long          {long_best}",
            f"worst_long         {long_worst}",
            "",
            f"radar_short_items  {short_summary['items']}",
            f"radar_short_pnl    R$ {_render_money(short_summary['pnl_total'])}",
            f"radar_short_hit    {_render_pct(short_summary['hit_rate'])}",
            f"radar_short_avg_move {_render_pct(short_summary['avg_return_pct'])}",
            f"best_short         {short_best}",
            f"worst_short        {short_worst}",
            "",
            f"radar_total_items  {radar_total_items}",
            f"radar_total_pnl    R$ {_render_money(radar_total_pnl)}",
            f"market_read        {market_read}",
            f"verdict            {verdict}",
        ]
    )
    return lines


def render_observation_review(payload: dict[str, Any]) -> str:
    if payload.get("status") == "NOT_COMPUTED":
        return _render_not_computed_review(payload)

    real_rows = payload["sections"]["real_watch_or_better"]["rows"]
    radar_rows = payload["sections"]["observation_top10"]["rows"]
    long_radar_rows = [row for row in radar_rows if row.get("direction") == "LONG"]
    short_radar_rows = [row for row in radar_rows if row.get("direction") == "SHORT"]
    real_long_rows = [row for row in real_rows if row.get("direction") == "LONG"]
    real_short_rows = [row for row in real_rows if row.get("direction") == "SHORT"]

    real_long_pnl = round(
        sum(_as_float(row.get("real_pnl")) for row in real_long_rows), 2
    )
    real_short_pnl = round(
        sum(_as_float(row.get("real_pnl")) for row in real_short_rows), 2
    )
    real_total_pnl = round(real_long_pnl + real_short_pnl, 2)
    radar_long_pnl = round(
        sum(_as_float(row.get("sim_pnl")) for row in long_radar_rows), 2
    )
    radar_short_pnl = round(
        sum(_as_float(row.get("sim_pnl")) for row in short_radar_rows), 2
    )
    radar_total_pnl = round(radar_long_pnl + radar_short_pnl, 2)
    market_read = _market_read(radar_long_pnl, radar_short_pnl)
    verdict = (
        "RADAR_GAIN"
        if radar_total_pnl > 0
        else "RADAR_LOSS" if radar_total_pnl < 0 else "FLAT"
    )

    lines = [
        "AURUM MTM REVIEW",
        "-" * 80,
        f"capital            R$ {_render_money(payload['capital'])}",
        f"real_pnl           R$ {_render_money(real_total_pnl)}",
        f"radar_pnl          R$ {_render_money(radar_total_pnl)}",
        f"verdict            {verdict}",
        "",
    ]
    lines.extend(_render_real_operations(real_rows))
    lines.append("")
    lines.extend(_render_radar_summary(long_radar_rows, short_radar_rows))
    if long_radar_rows:
        lines.append("")
        lines.extend(
            _render_table_rows(
                "RADAR LONG", long_radar_rows, limit=20, radar_section=True
            )
        )
    if short_radar_rows:
        lines.append("")
        lines.extend(
            _render_table_rows(
                "RADAR SHORT", short_radar_rows, limit=20, radar_section=True
            )
        )
    lines.append("")
    lines.extend(
        [
            "FINAL REVIEW",
            "-" * 80,
            f"real_long_pnl      R$ {_render_money(real_long_pnl)}",
            f"real_short_pnl     R$ {_render_money(real_short_pnl)}",
            f"real_total_pnl     R$ {_render_money(real_total_pnl)}",
            f"radar_long_pnl     R$ {_render_money(radar_long_pnl)}",
            f"radar_short_pnl    R$ {_render_money(radar_short_pnl)}",
            f"radar_total_pnl    R$ {_render_money(radar_total_pnl)}",
            f"combined_pnl       R$ {_render_money(real_total_pnl + radar_total_pnl)}",
            f"market_read        {market_read}",
            f"verdict            {verdict}",
        ]
    )
    return "\n".join(lines)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in REVIEW_COLUMNS})


def _write_not_computed_csv(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "status",
        "reason",
        "capital",
        "real_trades",
        "real_pnl",
        "observation_pnl",
        "long_pnl",
        "short_pnl",
        "data_missing",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "status": "NOT_COMPUTED",
                "reason": payload.get("cannot_compute_reason")
                or "Cannot compute MTM: missing reference prices from signal time.",
                "capital": payload.get("capital", 0.0),
                "real_trades": 0,
                "real_pnl": 0.0,
                "observation_pnl": "",
                "long_pnl": "",
                "short_pnl": "",
                "data_missing": payload.get("data_missing", 0),
            }
        )


def run_observation_review(
    *,
    run_dir: str | Path,
    capital: float = 10000.0,
    mode: str = "observation",
    prices_dir: str | Path = "data/prices",
    profile: str = "CON",
    relevance_pct: float = 0.5,
) -> dict[str, Any]:
    run_path = Path(run_dir)
    report_path = run_path / f"report_{profile}.json"
    if not report_path.exists():
        raise FileNotFoundError(f"Report JSON not found: {report_path}")

    payload = json.loads(report_path.read_text(encoding="utf-8-sig"))
    signal_date = _parse_signal_date(run_path)
    raw = _build_raw_rows(payload)
    rows_by_section: dict[str, list[dict[str, Any]]] = {}

    def materialize(
        section: str,
        raw_rows: list[dict[str, Any]],
        *,
        hypothetical: bool,
    ) -> list[dict[str, Any]]:
        notional = _allocate(capital, len(raw_rows))
        relevance_brl = max(0.0, notional * (relevance_pct / 100.0))
        section_rows: list[dict[str, Any]] = []
        for raw_row in raw_rows:
            row = _review_row(
                section=section,
                ticker=raw_row["ticker"],
                direction=raw_row["direction"],
                obs_class=raw_row["obs_class"],
                signal=raw_row["signal"],
                execution=raw_row["execution"],
                score=raw_row["score"],
                main_reason=raw_row["main_reason"],
                ref_price=raw_row.get("ref_price"),
                ref_date=_as_text(raw_row.get("ref_date"), ""),
                ref_ts=_as_text(raw_row.get("ref_ts"), ""),
                ref_source=_as_text(raw_row.get("ref_source"), ""),
                signal_date=signal_date,
                prices_dir=prices_dir,
                notional=notional,
                hypothetical=hypothetical,
                relevance_brl=relevance_brl,
            )
            section_rows.append(row)
        return section_rows

    for section, raw_rows in raw.items():
        rows_by_section[section] = materialize(
            section,
            raw_rows,
            hypothetical=section in {"long_observation", "short_observation"},
        )

    hypothetical_raw = raw.get("long_observation", []) + raw.get(
        "short_observation", []
    )
    signal_raw = raw.get("long_signals", []) + raw.get("short_signals", [])
    real_watch_raw = [
        row
        for row in signal_raw
        if row.get("execution")
        in {"READY", "WATCH", "SHORT_READY", "SHORT_MANUAL_ONLY"}
    ]
    blocked_raw = [
        row for row in signal_raw if row.get("execution") in {"BLOCKED", "DATA_BLOCKED"}
    ]
    top_long_observations = sorted(
        raw.get("long_observation", []),
        key=lambda row: _as_float(row.get("score")),
        reverse=True,
    )[:10]
    top_short_observations = sorted(
        raw.get("short_observation", []),
        key=lambda row: _as_float(row.get("score")),
        reverse=True,
    )[:10]
    observation_top10_raw = top_long_observations + top_short_observations

    rows_by_section["hypothetical_observation"] = materialize(
        "hypothetical_observation",
        hypothetical_raw,
        hypothetical=True,
    )
    rows_by_section["signal_review"] = materialize(
        "signal_review",
        signal_raw,
        hypothetical=False,
    )
    rows_by_section["real_watch_or_better"] = materialize(
        "real_watch_or_better",
        real_watch_raw,
        hypothetical=False,
    )
    rows_by_section["blocked_setups"] = materialize(
        "blocked_setups",
        blocked_raw,
        hypothetical=False,
    )
    rows_by_section["observation_top10"] = materialize(
        "observation_top10",
        observation_top10_raw,
        hypothetical=True,
    )
    all_rows = [row for rows in rows_by_section.values() for row in rows]
    visible_rows = (
        rows_by_section["real_watch_or_better"] + rows_by_section["observation_top10"]
    )

    txt_path = run_path / "observation_review.txt"
    csv_path = run_path / "observation_review.csv"
    json_path = run_path / "observation_review.json"
    data_missing = sum(
        1 for row in visible_rows if row.get("price_status") == "DATA_MISSING"
    )
    stale_prices = sum(1 for row in visible_rows if row.get("price_status") == "STALE")
    missing_reference = sum(
        1
        for row in visible_rows
        if row.get("price_status") == "DATA_MISSING"
        and "missing reference" in str(row.get("main_reason", "")).lower()
    )
    reviewed_rows = sum(
        1 for row in visible_rows if row.get("review_status") == "REVIEWED"
    )
    cannot_compute_reason = ""
    not_computed = (
        bool(visible_rows)
        and reviewed_rows == 0
        and missing_reference == len(visible_rows)
    )
    if not_computed:
        cannot_compute_reason = (
            "Cannot compute MTM: missing reference prices from signal time."
        )

    review: dict[str, Any] = {
        "schema_version": "observation_review.v1",
        "status": "NOT_COMPUTED" if not_computed else "COMPUTED",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_dir": str(run_path),
        "report_json": str(report_path),
        "prices_dir": str(prices_dir),
        "profile": profile,
        "mode": mode,
        "capital": round(float(capital), 2),
        "allocation_method": "equal_weight_per_section",
        "relevance_pct": relevance_pct,
        "sections": {
            section: {
                "summary": _section_summary(rows),
                "rows": rows,
            }
            for section, rows in rows_by_section.items()
        },
        "summary": {
            section: _section_summary(rows) for section, rows in rows_by_section.items()
        },
        "data_missing": data_missing,
        "stale_prices": stale_prices,
        "missing_reference": missing_reference,
        "reviewed_rows": reviewed_rows,
        "cannot_compute_reason": cannot_compute_reason,
        "outputs": {
            "txt": str(txt_path),
            "csv": str(csv_path),
            "json": str(json_path),
        },
    }
    if review["status"] == "NOT_COMPUTED":
        _write_not_computed_csv(csv_path, review)
    else:
        _write_csv(csv_path, all_rows)

    json_path.write_text(
        json.dumps(review, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    txt_path.write_text(render_observation_review(review), encoding="utf-8")
    return review
