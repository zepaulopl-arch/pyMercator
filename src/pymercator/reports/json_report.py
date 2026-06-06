from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pymercator.artifact_metadata import artifact_metadata
from pymercator.data.prices_csv import read_price_rows_csv
from pymercator.domain import DailyReport
from pymercator.explain import decision_codes, decision_label


def _enum_to_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    return value


def _convert(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _convert(item) for key, item in value.items()}

    if isinstance(value, tuple | list):
        return [_convert(item) for item in value]

    return _enum_to_value(value)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_text(value: Any, default: str = "") -> str:
    text = "" if value is None else str(value).strip()
    return text or default


def _normalize_ticker(ticker: Any) -> str:
    return _as_text(ticker, "").upper().replace(".SA", "")


def _price_file_for_ticker(prices_dir: str | Path, ticker: str) -> Path:
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


def _latest_reference_from_prices(
    ticker: str,
    prices_dir: str | Path,
    signal_ts: str,
) -> dict[str, Any]:
    try:
        price_path = _price_file_for_ticker(prices_dir, ticker)
        rows = read_price_rows_csv(price_path)
    except Exception:
        return {
            "ref_price": None,
            "ref_date": None,
            "ref_ts": None,
            "ref_source": "DATA_MISSING",
        }

    last_date = None
    last_close = 0.0
    for row in rows:
        date = _as_text(row.get("date"), "")
        close = _as_float(row.get("close"), default=0.0)
        if date and close > 0:
            last_date = date
            last_close = close

    if not last_date or last_close <= 0:
        return {
            "ref_price": None,
            "ref_date": None,
            "ref_ts": None,
            "ref_source": "DATA_MISSING",
        }

    return {
        "ref_price": round(last_close, 4),
        "ref_date": last_date,
        "ref_ts": signal_ts,
        "ref_source": str(price_path),
    }


def _prediction_global(prediction: dict[str, Any] | None) -> dict[str, Any]:
    if not prediction:
        return {}

    engine = prediction.get("engine") or prediction.get("engine_used")
    payload = {
        "engine": engine,
        "engine_used": engine,
        "horizons": prediction.get("horizons", []),
        "d5_score": prediction.get("d5_score"),
        "d20_score": prediction.get("d20_score"),
        "d60_score": prediction.get("d60_score"),
        "combined_score": prediction.get("combined_score"),
        "dominant_horizon": prediction.get("dominant_horizon"),
        "behavior": prediction.get("behavior"),
        "horizon_alignment": prediction.get("horizon_alignment"),
        "dominance_strength": prediction.get("dominance_strength"),
        "horizon_scores": prediction.get("horizon_scores"),
        "horizon_spread": prediction.get("horizon_spread"),
        "weights": prediction.get("weights", {}),
        "model_quality": prediction.get("model_quality", {}),
    }
    quality = payload.get("model_quality", {})
    if isinstance(quality, dict):
        payload["model_edge"] = quality.get("edge")
    return {key: value for key, value in payload.items() if value is not None}


def _prediction_for_decision(prediction: dict[str, Any] | None) -> dict[str, Any]:
    global_prediction = _prediction_global(prediction)
    return {
        key: global_prediction.get(key)
        for key in (
            "d5_score",
            "d20_score",
            "d60_score",
            "combined_score",
            "dominant_horizon",
            "behavior",
            "horizon_alignment",
            "dominance_strength",
        )
        if key in global_prediction
    }


def _generated_ts() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def _reference_fields(
    ticker: str,
    signal_ts: str,
    prices_dir: str | Path,
) -> dict[str, Any]:
    return _latest_reference_from_prices(ticker, prices_dir, signal_ts)


def _attach_reference(
    row: dict[str, Any],
    reference_by_ticker: dict[str, dict[str, Any]],
    prices_dir: str | Path,
    signal_ts: str,
) -> dict[str, Any]:
    result = dict(row)
    ticker = str(result.get("ticker", "")).upper().replace(".SA", "")
    reference = reference_by_ticker.get(ticker)
    if not reference and ticker:
        reference = _latest_reference_from_prices(ticker, prices_dir, signal_ts)
        reference_by_ticker[ticker] = reference
    if reference and result.get("ref_price") in (None, ""):
        result.update(reference)
    return result


def _attach_references_to_rows(
    rows: Any,
    reference_by_ticker: dict[str, dict[str, Any]],
    prices_dir: str | Path,
    signal_ts: str,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    return [
        _attach_reference(row, reference_by_ticker, prices_dir, signal_ts)
        for row in rows
        if isinstance(row, dict)
    ]


def daily_report_to_dict(
    report: DailyReport,
    prediction: dict[str, Any] | None = None,
    blockers_count: dict[str, int] | None = None,
    asset_blockers: dict[str, list[str]] | None = None,
    update_status: dict[str, Any] | None = None,
    basket: dict[str, Any] | None = None,
    observation_candidates: list[dict[str, Any]] | None = None,
    position_actions: dict[str, Any] | None = None,
    market_context: dict[str, Any] | None = None,
    prices_dir: str | Path = "data/prices",
) -> dict[str, Any]:
    signal_ts = _generated_ts()
    raw = _convert(asdict(report))
    raw["schema_version"] = "daily_report.v1"
    raw["runtime"] = artifact_metadata()
    raw["runtime"]["generated_at"] = signal_ts
    global_prediction = _prediction_global(prediction)
    decision_prediction = _prediction_for_decision(prediction)
    reference_by_ticker = {
        decision.asset.ticker.upper().replace(".SA", ""): _reference_fields(
            decision.asset.ticker,
            signal_ts,
            prices_dir,
        )
        for decision in report.decisions
    }

    if global_prediction:
        raw["prediction"] = global_prediction
        quality = global_prediction.get("model_quality", {})
        if isinstance(quality, dict):
            raw["model_quality"] = quality.get("status")
            raw["model_edge"] = quality.get("edge")
    else:
        raw["prediction"] = {}
        raw["model_quality"] = raw.get("model_quality", "")

    if blockers_count is not None:
        raw["blockers_count"] = dict(blockers_count)
        raw["blockers"] = dict(blockers_count)
    else:
        raw["blockers_count"] = {}
        raw["blockers"] = {}

    raw["decision"] = {
        "actionable": sum(
            1
            for decision in report.decisions
            if str(decision.permission.status.value).upper() == "READY"
        ),
        "watch": sum(
            1
            for decision in report.decisions
            if str(decision.permission.status.value).upper() == "WATCH"
        ),
        "blocked": sum(
            1
            for decision in report.decisions
            if str(decision.permission.status.value).upper() == "BLOCKED"
        ),
        "rejected": 0,
    }

    if update_status:
        raw["update_status"] = dict(update_status)
    else:
        raw["update_status"] = {}

    if market_context:
        raw["market_context"] = _convert(market_context)
    else:
        raw["market_context"] = {}

    if basket is not None:
        raw["basket"] = dict(basket)
    else:
        raw["basket"] = {}

    if observation_candidates is not None:
        raw["observation_candidates"] = _attach_references_to_rows(
            _convert(observation_candidates),
            reference_by_ticker,
            prices_dir,
            signal_ts,
        )
    else:
        raw["observation_candidates"] = []

    if position_actions is not None:
        converted_actions = _convert(position_actions)
        converted_actions.setdefault("schema_version", "position_actions.v1")
        converted_actions["short_candidates"] = _attach_references_to_rows(
            converted_actions.get("short_candidates", []),
            reference_by_ticker,
            prices_dir,
            signal_ts,
        )
        converted_actions["short_observation_candidates"] = _attach_references_to_rows(
            converted_actions.get("short_observation_candidates", []),
            reference_by_ticker,
            prices_dir,
            signal_ts,
        )
        converted_actions["short_book"] = _attach_references_to_rows(
            converted_actions.get("short_book", []),
            reference_by_ticker,
            prices_dir,
            signal_ts,
        )
        defensive_book = converted_actions.get("defensive_book", {})
        if isinstance(defensive_book, dict):
            defensive_book["short_candidates"] = _attach_references_to_rows(
                defensive_book.get("short_candidates", []),
                reference_by_ticker,
                prices_dir,
                signal_ts,
            )
            converted_actions["defensive_book"] = defensive_book
        raw["position_actions"] = converted_actions
        raw["exit_book"] = converted_actions.get("exit_book", {})
        raw["defensive_book"] = converted_actions.get("defensive_book", {})
        raw["short_candidates"] = converted_actions.get("short_candidates", [])
        raw["short_observation_candidates"] = converted_actions.get(
            "short_observation_candidates",
            [],
        )
        raw["hedge_candidates"] = converted_actions.get("hedge_candidates", [])
    else:
        raw["position_actions"] = {"schema_version": "position_actions.v1"}
        raw["short_observation_candidates"] = []

    for index, decision in enumerate(report.decisions):
        ticker = decision.asset.ticker
        raw["decisions"][index].update(
            reference_by_ticker.get(ticker.upper().replace(".SA", ""), {})
        )
        raw["decisions"][index]["decision_codes"] = list(decision_codes(decision))
        raw["decisions"][index]["decision_label"] = decision_label(decision)
        raw["decisions"][index]["blocker_reasons"] = list(
            (asset_blockers or {}).get(ticker, [])
        )
        if decision_prediction:
            raw["decisions"][index]["prediction"] = dict(decision_prediction)

    return raw


def render_daily_report_json(
    report: DailyReport,
    indent: int = 2,
    prediction: dict[str, Any] | None = None,
    blockers_count: dict[str, int] | None = None,
    asset_blockers: dict[str, list[str]] | None = None,
    update_status: dict[str, Any] | None = None,
    basket: dict[str, Any] | None = None,
    observation_candidates: list[dict[str, Any]] | None = None,
    position_actions: dict[str, Any] | None = None,
    market_context: dict[str, Any] | None = None,
    prices_dir: str | Path = "data/prices",
) -> str:
    payload = daily_report_to_dict(
        report,
        prediction=prediction,
        blockers_count=blockers_count,
        asset_blockers=asset_blockers,
        update_status=update_status,
        basket=basket,
        observation_candidates=observation_candidates,
        position_actions=position_actions,
        market_context=market_context,
        prices_dir=prices_dir,
    )
    return json.dumps(payload, ensure_ascii=False, indent=indent)


def write_daily_report_json(
    report: DailyReport,
    path: str | Path,
    prediction: dict[str, Any] | None = None,
    blockers_count: dict[str, int] | None = None,
    asset_blockers: dict[str, list[str]] | None = None,
    update_status: dict[str, Any] | None = None,
    basket: dict[str, Any] | None = None,
    observation_candidates: list[dict[str, Any]] | None = None,
    position_actions: dict[str, Any] | None = None,
    market_context: dict[str, Any] | None = None,
    prices_dir: str | Path = "data/prices",
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_daily_report_json(
            report,
            prediction=prediction,
            blockers_count=blockers_count,
            asset_blockers=asset_blockers,
            update_status=update_status,
            basket=basket,
            observation_candidates=observation_candidates,
            position_actions=position_actions,
            market_context=market_context,
            prices_dir=prices_dir,
        ),
        encoding="utf-8",
    )
