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
    "reference_date",
    "reference_price",
    "current_date",
    "current_price",
    "return_pct",
    "notional",
    "pnl_long",
    "pnl_short",
    "pnl",
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
) -> PricePoint | None:
    if fallback_price and fallback_price > 0:
        for point in reversed(points):
            if abs(point.close - fallback_price) <= max(0.01, fallback_price * 0.0005):
                return PricePoint(date=point.date, close=fallback_price)
        return PricePoint(date=signal_date, close=fallback_price)

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
    asset = item.get("asset", {}) if isinstance(item.get("asset"), dict) else {}
    value = _as_float(asset.get("last_close"), default=0.0)
    return value if value > 0 else None


def _decision_reason(item: dict[str, Any]) -> str:
    reasons = item.get("blocker_reasons")
    if isinstance(reasons, list) and reasons:
        return "+".join(_as_text(reason) for reason in reasons)
    return _as_text(item.get("decision_label"))


def _decision_execution(item: dict[str, Any]) -> str:
    permission = item.get("permission", {}) if isinstance(item.get("permission"), dict) else {}
    validation = item.get("validation", {}) if isinstance(item.get("validation"), dict) else {}
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
    return _as_text(item.get("borrow_reason") or item.get("reason") or item.get("setup_reason"))


def _classify_block(direction: str, pnl: float, *, relevance_brl: float) -> str:
    if pnl > relevance_brl:
        return "MISSED_OPPORTUNITY"
    if pnl < -relevance_brl:
        return "GOOD_BLOCK"
    return "NEUTRAL_BLOCK"


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
    reference_price: float | None,
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
        "reference_date": "-",
        "reference_price": None,
        "current_date": "-",
        "current_price": None,
        "return_pct": None,
        "notional": round(notional, 2),
        "pnl_long": 0.0,
        "pnl_short": 0.0,
        "pnl": 0.0,
        "real_pnl": 0.0,
        "review_status": "OK",
        "review_class": "-",
        "hypothetical": hypothetical,
    }

    try:
        points = _read_price_points(prices_dir, ticker)
    except Exception as exc:
        row["review_status"] = "DATA_MISSING"
        row["review_class"] = "DATA_MISSING"
        row["main_reason"] = f"price data missing: {exc}"
        return row

    ref = _reference_point(
        points=points,
        fallback_price=reference_price,
        signal_date=signal_date,
    )
    current = _current_point(points)
    if ref is None or current is None:
        row["review_status"] = "DATA_MISSING"
        row["review_class"] = "DATA_MISSING"
        row["main_reason"] = "price data missing"
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
            "real_pnl": round(real_pnl, 2),
        }
    )
    if section == "blocked_setups":
        row["review_class"] = _classify_block(
            direction,
            pnl,
            relevance_brl=relevance_brl,
        )
    return row


def _allocate(capital: float, count: int) -> float:
    return capital / count if count > 0 else 0.0


def _build_raw_rows(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    decisions = payload.get("decisions", []) or []
    decision_by_ticker = _decision_index(payload)

    long_observations: list[dict[str, Any]] = []
    for item in payload.get("observation_candidates", []) or []:
        ticker = _normalize_ticker(item.get("ticker"))
        decision = decision_by_ticker.get(ticker, {})
        long_observations.append(
            {
                "ticker": ticker,
                "direction": "LONG",
                "obs_class": _as_text(item.get("class"), "WATCH").replace("OBS_READY", "OBS_FAVORABLE"),
                "signal": _long_signal(decision) if decision else "BUY_SETUP",
                "execution": _decision_execution(decision) if decision else "WATCH",
                "score": _as_float(item.get("score") or item.get("obs_index")),
                "main_reason": _decision_reason(decision) if decision else _as_text(item.get("reason")),
                "reference_price": _decision_reference_price(decision) if decision else None,
            }
        )

    short_observation_source = payload.get("short_observation_candidates", []) or []
    if not short_observation_source:
        short_observation_source = payload.get("short_candidates", []) or []
    if not short_observation_source:
        defensive = payload.get("defensive_book", {}) if isinstance(payload.get("defensive_book"), dict) else {}
        short_observation_source = defensive.get("short_candidates", []) or []

    short_observations: list[dict[str, Any]] = []
    for item in short_observation_source:
        if not isinstance(item, dict):
            continue
        execution = _short_execution(item)
        short_observations.append(
            {
                "ticker": _normalize_ticker(item.get("ticker")),
                "direction": "SHORT",
                "obs_class": _as_text(item.get("class"), "SHORT_SETUP"),
                "signal": "SELL_SETUP",
                "execution": execution,
                "score": _as_float(item.get("score") or item.get("short_score")),
                "main_reason": _short_reason(item, execution),
                "reference_price": _decision_reference_price(
                    decision_by_ticker.get(_normalize_ticker(item.get("ticker")), {})
                ),
            }
        )

    real_trades: list[dict[str, Any]] = []
    blocked_setups: list[dict[str, Any]] = []
    for item in decisions:
        if not isinstance(item, dict):
            continue
        execution = _decision_execution(item)
        ticker = _decision_ticker(item)
        row = {
            "ticker": ticker,
            "direction": "LONG",
            "obs_class": "SIGNAL",
            "signal": _long_signal(item),
            "execution": execution,
            "score": _decision_score(item),
            "main_reason": _decision_reason(item),
            "reference_price": _decision_reference_price(item),
        }
        if execution == "READY":
            real_trades.append(row)
        elif execution in {"BLOCKED", "DATA_BLOCKED"}:
            blocked_setups.append(row)

    short_candidates = payload.get("short_candidates", []) or []
    defensive = payload.get("defensive_book", {}) if isinstance(payload.get("defensive_book"), dict) else {}
    if not short_candidates:
        short_candidates = defensive.get("short_candidates", []) or []
    for item in short_candidates:
        if not isinstance(item, dict):
            continue
        execution = _short_execution(item)
        ticker = _normalize_ticker(item.get("ticker"))
        row = {
            "ticker": ticker,
            "direction": "SHORT",
            "obs_class": _as_text(item.get("class"), "SHORT_SETUP"),
            "signal": "SELL_SETUP",
            "execution": execution,
            "score": _as_float(item.get("score") or item.get("short_score")),
            "main_reason": _short_reason(item, execution),
            "reference_price": _decision_reference_price(decision_by_ticker.get(ticker, {})),
        }
        if execution == "READY" and bool(item.get("executable")):
            real_trades.append(row)
        elif execution in {"BLOCKED", "DATA_BLOCKED"}:
            blocked_setups.append(row)

    return {
        "long_observation": long_observations,
        "short_observation": short_observations,
        "real_trades": real_trades,
        "blocked_setups": blocked_setups,
    }


def _section_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in rows if row.get("review_status") != "DATA_MISSING"]
    wins = [row for row in valid if _as_float(row.get("pnl")) > 0]
    total_pnl = sum(_as_float(row.get("pnl")) for row in valid)
    real_pnl = sum(_as_float(row.get("real_pnl")) for row in valid)
    returns = [_as_float(row.get("return_pct")) for row in valid if row.get("return_pct") is not None]
    classes: dict[str, int] = {}
    for row in rows:
        klass = _as_text(row.get("review_class"))
        classes[klass] = classes.get(klass, 0) + 1
    return {
        "items": len(rows),
        "valid_items": len(valid),
        "data_missing": len(rows) - len(valid),
        "hit_rate": round((len(wins) / len(valid)) * 100.0, 2) if valid else 0.0,
        "avg_return_pct": round(sum(returns) / len(returns), 4) if returns else 0.0,
        "pnl_total": round(total_pnl, 2),
        "real_pnl": round(real_pnl, 2),
        "classes": classes,
    }


def _render_money(value: Any) -> str:
    return f"{_as_float(value):,.2f}"


def _render_pct(value: Any) -> str:
    if value is None:
        return "-"
    return f"{_as_float(value):.2f}%"


def _render_rows(title: str, rows: list[dict[str, Any]], limit: int = 12) -> list[str]:
    lines = [title, "-" * 80]
    summary = _section_summary(rows)
    lines.append(
        "items {items} | valid {valid_items} | hit_rate {hit_rate:.2f}% | "
        "avg_return {avg_return_pct:.2f}% | pnl R$ {pnl}".format(
            pnl=_render_money(summary["pnl_total"]),
            **summary,
        )
    )
    lines.append("")
    lines.append(
        f"{'#':>2}  {'TICKER':<8} {'DIR':<5} {'EXECUTION':<12} "
        f"{'RET':>8} {'PNL':>12} {'CLASS':<18} MAIN_REASON"
    )
    if not rows:
        lines.append("status             EMPTY")
        lines.append("reason             no items")
        return lines
    for index, row in enumerate(rows[:limit], start=1):
        lines.append(
            f"{index:>2}  {row['ticker']:<8} {row['direction']:<5} "
            f"{row['execution']:<12} {_render_pct(row.get('return_pct')):>8} "
            f"{_render_money(row.get('pnl')):>12} {row['review_class']:<18} "
            f"{row['main_reason']}"
        )
    if len(rows) > limit:
        lines.append(f"... {len(rows) - limit} more rows in observation_review.csv")
    return lines


def render_observation_review(payload: dict[str, Any]) -> str:
    summaries = payload["summary"]
    lines = [
        "AURUM OBSERVATION REVIEW",
        "-" * 80,
        f"run_dir            {payload['run_dir']}",
        f"capital            R$ {_render_money(payload['capital'])}",
        f"mode               {payload['mode']}",
        "note               observation P&L is hypothetical; it is not a real trade record",
        "",
        *_render_rows(
            "LONG OBSERVATION RESULT",
            payload["sections"]["long_observation"]["rows"],
        ),
        "",
        *_render_rows(
            "SHORT OBSERVATION RESULT",
            payload["sections"]["short_observation"]["rows"],
        ),
        "",
        *_render_rows(
            "BLOCKED SIGNAL REVIEW",
            payload["sections"]["blocked_setups"]["rows"],
        ),
        "",
        "FINAL REVIEW",
        "-" * 80,
        f"real_pnl           R$ {_render_money(summaries['real_trades']['real_pnl'])}",
        f"long_observation   R$ {_render_money(summaries['long_observation']['pnl_total'])}",
        f"short_observation  R$ {_render_money(summaries['short_observation']['pnl_total'])}",
        f"blocked_setups     R$ {_render_money(summaries['blocked_setups']['pnl_total'])}",
        f"good_blocks        {summaries['blocked_setups']['classes'].get('GOOD_BLOCK', 0)}",
        f"missed_opportunity {summaries['blocked_setups']['classes'].get('MISSED_OPPORTUNITY', 0)}",
        f"data_missing       {payload['data_missing']}",
        "",
        "FILES",
        "-" * 80,
        f"txt                {payload['outputs']['txt']}",
        f"csv                {payload['outputs']['csv']}",
        f"json               {payload['outputs']['json']}",
    ]
    return "\n".join(lines)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in REVIEW_COLUMNS})


def run_observation_review(
    *,
    run_dir: str | Path,
    capital: float = 100000.0,
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
    all_rows: list[dict[str, Any]] = []

    for section, raw_rows in raw.items():
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
                reference_price=raw_row["reference_price"],
                signal_date=signal_date,
                prices_dir=prices_dir,
                notional=notional,
                hypothetical=section != "real_trades",
                relevance_brl=relevance_brl,
            )
            section_rows.append(row)
            all_rows.append(row)
        rows_by_section[section] = section_rows

    hypothetical_rows = (
        rows_by_section.get("long_observation", [])
        + rows_by_section.get("short_observation", [])
    )

    txt_path = run_path / "observation_review.txt"
    csv_path = run_path / "observation_review.csv"
    json_path = run_path / "observation_review.json"

    review: dict[str, Any] = {
        "schema_version": "observation_review.v1",
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
            section: _section_summary(rows)
            for section, rows in rows_by_section.items()
        },
        "data_missing": sum(1 for row in all_rows if row.get("review_status") == "DATA_MISSING"),
        "outputs": {
            "txt": str(txt_path),
            "csv": str(csv_path),
            "json": str(json_path),
        },
    }
    review["sections"]["hypothetical_observation"] = {
        "summary": _section_summary(hypothetical_rows),
        "rows": hypothetical_rows,
    }
    review["summary"]["hypothetical_observation"] = _section_summary(hypothetical_rows)

    _write_csv(csv_path, all_rows)
    json_path.write_text(
        json.dumps(review, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    txt_path.write_text(render_observation_review(review), encoding="utf-8")
    return review
