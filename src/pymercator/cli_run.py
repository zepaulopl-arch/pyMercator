from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

from pymercator import model_governance as governance
from pymercator.basket import run_daily_basket
from pymercator.domain import DailyReport, ExecutionStatus
from pymercator.explain import decision_codes, decision_label
from pymercator.horizon_observer import (
    dominance_strength,
    horizon_alignment,
    horizon_spread,
    normalize_horizon_scores,
)
from pymercator.market_context import load_market_context
from pymercator.observation import observation_from_decisions, render_observation_candidates
from pymercator.pipeline import run_daily_pipeline
from pymercator.position_actions import build_position_actions, render_position_books
from pymercator.policy import normalize_profile
from pymercator.reports.json_report import daily_report_to_dict, write_daily_report_json
from pymercator.reports.terminal import render_daily_report
from pymercator.top_reasons import (
    TOP_REASONS_WIDTH,
    format_top_reason_legend,
    format_top_reasons,
)
from pymercator.update_freshness import build_data_freshness
from pymercator.ui import colorize, format_kv_section, muted_line, truncate


def _count_status(report: DailyReport, status: ExecutionStatus) -> int:
    return sum(1 for item in report.decisions if item.permission.status == status)


def _tickers_by_status(report: DailyReport, status: ExecutionStatus) -> list[str]:
    return [
        item.asset.ticker
        for item in report.decisions
        if item.permission.status == status
    ]


def _candidates_by_status(
    report: DailyReport,
    status: ExecutionStatus,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, item in enumerate(report.decisions, start=1):
        if item.permission.status != status:
            continue
        candidates.append(
            {
                "ticker": item.asset.ticker,
                "score": item.ranking.context_score,
                "rank": index,
                "source": "daily_run",
            }
        )
    return candidates


STATUS_ONLY_CODES = {"OK", "CAUTION", "BLOCKED", "UNKNOWN"}
GLOBAL_BLOCKER_PRIORITY = (
    "MODEL_WEAK",
    "RISK_OFF",
    "BEHAVIOR_AVOID",
    "REGIME_DENY",
    "VOL_HIGH",
)
BLOCKING_MODEL_QUALITY = {"WEAK", "DEGENERATE"}


def _dedupe(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item for item in values if item))


def _compact_decimal(value: Any, precision: int) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    text = f"{number:.{precision}f}"
    return text[1:] if text.startswith("0.") else text


def _horizon_sort_key(value: Any) -> int:
    try:
        return int(str(value).upper().removeprefix("D"))
    except ValueError:
        return 999


def format_observer_weights(weights: dict[str, Any]) -> str:
    if not isinstance(weights, dict) or not weights:
        return "-"
    parts = []
    for horizon in sorted(weights, key=_horizon_sort_key):
        parts.append(f"{str(horizon).upper()}={_compact_decimal(weights[horizon], 3)}")
    return " ".join(parts)


def _model_quality_status(prediction: dict[str, Any]) -> str:
    quality = prediction.get("model_quality", {})
    if not isinstance(quality, dict):
        return ""
    return str(quality.get("status", "")).strip().upper()


def _prediction_behavior(prediction: dict[str, Any]) -> str:
    return str(prediction.get("behavior", "")).strip().upper()


def _load_model_quality_governance(policy: str) -> dict[str, Any]:
    default = {
        "WEAK": {
            "action": "BLOCK",
            "reason_code": "MODEL_WEAK",
            "reason": "model quality is weak",
            "allow_watch": False,
            "basket_status": "BLOCKED",
        },
        "DEGENERATE": {
            "action": "BLOCK",
            "reason_code": "MODEL_WEAK",
            "reason": "model quality is degenerate",
            "allow_watch": False,
            "basket_status": "BLOCKED",
        },
    }
    try:
        payload = json.loads(Path(policy).read_text(encoding="utf-8-sig"))
    except Exception:
        return default
    if not isinstance(payload, dict):
        return default
    governance = payload.get("model_quality_governance", default)
    if not isinstance(governance, dict):
        return default
    merged = dict(default)
    merged.update(governance)
    return merged


def _global_blockers(report: DailyReport, prediction: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if _model_quality_status(prediction) in BLOCKING_MODEL_QUALITY:
        blockers.append("MODEL_WEAK")
    if report.market_regime.regime.value == "RISK_OFF":
        blockers.append("RISK_OFF")
    if _prediction_behavior(prediction) == "AVOID":
        blockers.append("BEHAVIOR_AVOID")
    return list(_dedupe(tuple(blockers)))


def _ordered_blockers(codes: list[str]) -> list[str]:
    priority = {code: index for index, code in enumerate(GLOBAL_BLOCKER_PRIORITY)}
    unique = list(_dedupe(tuple(codes)))
    return sorted(unique, key=lambda code: (priority.get(code, 999), code))


def _blockers_for_decision(
    decision: Any,
    report: DailyReport,
    prediction: dict[str, Any],
) -> list[str]:
    codes = _global_blockers(report, prediction)
    codes.extend(
        code
        for code in decision_codes(decision)
        if code not in STATUS_ONLY_CODES
    )
    return _ordered_blockers(codes)


def _asset_blockers(
    report: DailyReport,
    prediction: dict[str, Any],
) -> dict[str, list[str]]:
    return {
        decision.asset.ticker: _blockers_for_decision(decision, report, prediction)
        for decision in report.decisions
    }


def _blocker_counts(blockers_by_asset: dict[str, list[str]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for blockers in blockers_by_asset.values():
        counts.update(blockers)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _load_prediction_observer(path: str) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {}

    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"engine_used": "-", "error": str(exc), "source": path}
    if not isinstance(payload, dict):
        return {}

    if payload.get("engine_used") != "multi_horizon_ridge":
        return {
            "engine_used": payload.get("engine_used", "-"),
            "is_baseline": bool(payload.get("is_baseline", False)),
            "status": payload.get("status"),
            "experimental": bool(payload.get("experimental", False)),
            "reason": payload.get("reason", ""),
        }

    observer = payload.get("horizon_observer", {})
    if not isinstance(observer, dict):
        observer = {}
    observer_config = payload.get("observer", {})
    if not isinstance(observer_config, dict):
        observer_config = {}

    scores = observer.get("scores", {})
    if not isinstance(scores, dict):
        scores = {}
    horizon_scores = normalize_horizon_scores(
        payload.get("horizon_scores")
        if isinstance(payload.get("horizon_scores"), dict)
        else observer.get("horizon_scores", scores)
    )
    weights = observer.get("weights", payload.get("weights", {}))
    if not isinstance(weights, dict):
        weights = {}

    return {
        "engine_used": "multi_horizon_ridge",
        "is_baseline": False,
        "status": payload.get("status"),
        "experimental": bool(payload.get("experimental", False)),
        "reason": payload.get("reason", ""),
        "horizons": payload.get("horizons", []),
        "observer_mode": observer.get("mode", observer_config.get("mode", "-")),
        "weights": weights,
        "horizon_scores": horizon_scores,
        "horizon_spread": payload.get(
            "horizon_spread",
            observer.get("horizon_spread", horizon_spread(horizon_scores)),
        ),
        "horizon_alignment": payload.get(
            "horizon_alignment",
            observer.get("horizon_alignment", horizon_alignment(horizon_scores)),
        ),
        "dominance_strength": payload.get(
            "dominance_strength",
            observer.get("dominance_strength", dominance_strength(horizon_scores)),
        ),
        "d5_score": horizon_scores.get("D5"),
        "d20_score": horizon_scores.get("D20"),
        "d60_score": horizon_scores.get("D60"),
        "combined_score": observer.get("combined_score"),
        "dominant_horizon": observer.get("dominant_horizon"),
        "behavior": observer.get("behavior"),
        "model_quality": payload.get("model_quality", {}),
        "source": path,
    }


def _top_rows_with_prediction(
    report: DailyReport,
    limit: int,
    prediction: dict[str, Any],
) -> list[dict[str, Any]]:
    prediction_fields = {
        "d5_score": prediction.get("d5_score"),
        "d20_score": prediction.get("d20_score"),
        "d60_score": prediction.get("d60_score"),
        "combined_score": prediction.get("combined_score"),
        "dominant_horizon": prediction.get("dominant_horizon"),
        "behavior": prediction.get("behavior"),
        "horizon_alignment": prediction.get("horizon_alignment"),
        "dominance_strength": prediction.get("dominance_strength"),
    }
    rows: list[dict[str, Any]] = []
    for item in report.decisions[:limit]:
        blockers = governance.blockers_for_decision(item, report, prediction)
        row = {
            "ticker": item.asset.ticker,
            "decision": item.permission.status.value,
            "score": item.ranking.context_score,
            "guard": "+".join(blockers) if blockers else decision_label(item),
            "blockers": blockers,
        }
        if prediction and prediction.get("engine_used") == "multi_horizon_ridge":
            row.update(prediction_fields)
        rows.append(row)
    return rows


def _blocked_payload(
    *,
    profile: str,
    list_name: str,
    reason: str,
    files: dict[str, str],
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "command": "run",
        "profile": profile,
        "list": list_name.upper(),
        "status": "BLOCKED",
        "reason": reason,
        "detail": detail or {},
        "files": files,
    }


def _apply_model_quality_guard(
    report: DailyReport,
    prediction: dict[str, Any],
    policy: str,
) -> DailyReport:
    quality_status = _model_quality_status(prediction)
    if quality_status not in BLOCKING_MODEL_QUALITY:
        return report

    governance = _load_model_quality_governance(policy)
    weak_policy = governance.get(quality_status, governance.get("WEAK", {}))
    if not isinstance(weak_policy, dict):
        weak_policy = {}
    action = str(weak_policy.get("action", "BLOCK")).strip().upper()
    reason_code = str(weak_policy.get("reason_code", "MODEL_WEAK")).strip().upper()
    reason_text = str(weak_policy.get("reason", "model quality is weak")).strip()
    reason = f"{reason_code}: {reason_text}"

    if action != "BLOCK":
        return report

    decisions = []
    for decision in report.decisions:
        permission = replace(
            decision.permission,
            status=ExecutionStatus.BLOCKED,
            max_position_factor=0.0,
            reasons=_dedupe((
                *decision.permission.reasons,
                reason,
            )),
        )
        decisions.append(replace(decision, permission=permission))

    return replace(
        report,
        decisions=tuple(decisions),
        posture="STAND_ASIDE",
        reasons=_dedupe((
            *report.reasons,
            f"{reason}; operations blocked",
        )),
    )


def _apply_prediction_behavior_guard(
    report: DailyReport,
    prediction: dict[str, Any],
) -> DailyReport:
    if _prediction_behavior(prediction) != "AVOID":
        return report

    reason = "BEHAVIOR_AVOID: behavior is AVOID"
    decisions = []
    for decision in report.decisions:
        permission = replace(
            decision.permission,
            status=ExecutionStatus.BLOCKED,
            max_position_factor=0.0,
            reasons=_dedupe((
                *decision.permission.reasons,
                reason,
            )),
        )
        decisions.append(replace(decision, permission=permission))

    return replace(
        report,
        decisions=tuple(decisions),
        posture="STAND_ASIDE",
        reasons=_dedupe((
            *report.reasons,
            f"{reason}; operations blocked",
        )),
    )


def _load_operational_market_context(path: str) -> dict[str, Any]:
    source = Path(path)
    raw = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError("market context must be a JSON object")

    context = load_market_context(source)
    errors: list[str] = []

    for field in ("market_trend", "market_volatility"):
        if field not in raw:
            errors.append(f"missing {field}")

    if context.get("market_trend") == "UNKNOWN":
        errors.append("market_trend is UNKNOWN")

    if errors:
        raise ValueError("; ".join(errors))

    return context


def _update_status_path_for_context(context_path: str) -> Path:
    return Path(context_path).with_name("latest_update_status.json")


def _load_update_status(context_path: str) -> dict[str, Any]:
    source = _update_status_path_for_context(context_path)
    if not source.exists():
        return {
            "schema_version": "update_status.v1",
            "status": "UNKNOWN",
            "impact": "UNKNOWN",
            "context_valid": "UNKNOWN",
            "regime_reliability": "UNKNOWN",
            "freshness": build_data_freshness([]),
            "source": str(source),
        }
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"status": "UNKNOWN", "error": str(exc), "source": str(source)}
    if not isinstance(payload, dict):
        return {
            "status": "UNKNOWN",
            "error": "update status must be a JSON object",
            "source": str(source),
        }
    payload.setdefault("schema_version", "update_status.v1")
    payload.setdefault("freshness", build_data_freshness([]))
    payload.setdefault("source", str(source))
    return payload


def run_decision_flow(
    *,
    profile: str = "CON",
    list_name: str = "IBOV",
    policy: str = "config/policy.json",
    universe: str = "data/universes/ibov_live.csv",
    context: str = "storage/context/latest_market_context.json",
    matrix: str = "storage/features/latest_feature_matrix.csv",
    evaluation: str = "storage/prediction/latest_evaluation.json",
    prices_dir: str = "data/prices",
    observation_config: str = "config/observation.json",
    positions: str = "storage/positions/current_positions.csv",
    borrow_data: str = "storage/borrow/latest_borrow_data.csv",
    limit: int = 20,
    run_dir: str = "storage/runs/latest",
    report_output: str = "storage/reports/latest_daily_report.txt",
    json_output: str = "storage/reports/latest_daily_report.json",
    basket: bool = False,
    slots: int = 5,
    min_sectors: int = 3,
    min_weight: float = 0.10,
    capital: float = 100000.0,
    risk_per_trade: float = 0.005,
    targets: int = 2,
    stop: str = "progressive",
    basket_output: str = "storage/baskets/latest_daily_basket.csv",
    allow_experimental_model: bool = False,
) -> dict[str, Any]:
    normalized_profile = normalize_profile(profile)
    files = {
        "context": context,
        "universe": universe,
        "matrix": matrix,
        "evaluation": evaluation,
        "report": report_output,
        "json": json_output,
        "run_dir": run_dir,
        "basket": basket_output,
        "update_status": str(_update_status_path_for_context(context)),
        "positions": positions,
        "borrow_data": borrow_data,
    }

    try:
        context_payload = _load_operational_market_context(context)
    except Exception as exc:
        return _blocked_payload(
            profile=normalized_profile,
            list_name=list_name,
            reason="invalid or insufficient market context",
            files=files,
            detail={"error": str(exc), "context": context},
        )

    update_status_payload = _load_update_status(context)
    prediction_payload = _load_prediction_observer(evaluation)
    if prediction_payload.get("status") and prediction_payload.get("status") != "OK":
        return _blocked_payload(
            profile=normalized_profile,
            list_name=list_name,
            reason="invalid prediction evaluation",
            files=files,
            detail={"evaluation": evaluation, "prediction": prediction_payload},
        )
    if prediction_payload.get("experimental") and not allow_experimental_model:
        return _blocked_payload(
            profile=normalized_profile,
            list_name=list_name,
            reason="experimental prediction evaluation requires --allow-experimental-model",
            files=files,
            detail={"evaluation": evaluation, "prediction": prediction_payload},
        )

    try:
        report = run_daily_pipeline(
            universe_path=universe,
            universe_name=list_name.upper(),
            profile=normalized_profile,
            headline_risk="OFF",
            headline_tags=context_payload["headline_tags"],
            market_trend=context_payload["market_trend"],
            market_volatility=context_payload["market_volatility"],
            policy_path=policy,
        )

        if report.market_regime.regime.value == "UNKNOWN":
            return _blocked_payload(
                profile=normalized_profile,
                list_name=list_name,
                reason="invalid or insufficient market context",
                files=files,
                detail={
                    "context": context_payload,
                    "regime_reasons": list(report.market_regime.reasons),
                },
            )

        report = governance.apply_model_quality_guard(report, prediction_payload, policy)
        report = governance.apply_prediction_behavior_guard(report, prediction_payload)
        asset_blockers = governance.asset_blockers(report, prediction_payload)
        blockers_count = governance.blocker_counts(asset_blockers)

        rendered = render_daily_report(report, limit=limit)
        report_path = Path(report_output)
        json_path = Path(json_output)
        run_path = Path(run_dir)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        run_path.mkdir(parents=True, exist_ok=True)

        report_path.write_text(rendered, encoding="utf-8")
        (run_path / "report.txt").write_text(rendered, encoding="utf-8")

        ready_candidates = _candidates_by_status(report, ExecutionStatus.READY)
        ready_tickers = [item["ticker"] for item in ready_candidates]
        observation_payload = observation_from_decisions(
            report.decisions,
            config_path=observation_config,
        )
        observation_candidates: list[dict[str, Any]] = []
        if (
            not ready_tickers
            and observation_payload.get("enabled", True)
            and observation_payload.get("show_when_no_actionable", True)
        ):
            observation_candidates = list(observation_payload.get("candidates", []))
        position_actions = build_position_actions(
            report,
            prediction_payload,
            positions_path=positions,
            borrow_data_path=borrow_data,
            long_limit=min(10, max(1, limit)),
            short_limit=min(10, max(1, limit)),
        )

        basket_payload: dict[str, Any] | None = None
        if basket:
            basket_payload = run_daily_basket(
                slots=slots,
                min_sectors=min_sectors,
                min_weight=min_weight,
                capital=capital,
                risk_per_trade=risk_per_trade,
                targets=targets,
                stop_mode=stop,
                prices_dir=prices_dir,
                universe=universe,
                matrix=matrix,
                evaluation=evaluation,
                output_csv=basket_output,
                eligible_tickers=ready_tickers,
                ordered_candidates=ready_candidates,
                blocked_reason="no actionable assets",
            )

        basket_summary = None
        if basket_payload is not None:
            basket_summary = {
                "status": basket_payload.get("status", "-"),
                "slots": basket_payload.get("slots", slots),
                "assets": len(basket_payload.get("rows", [])),
                "reason": basket_payload.get("reason", ""),
                "output": basket_payload.get("output_csv", basket_output),
            }

        write_daily_report_json(
            report,
            json_path,
            prediction=prediction_payload,
            blockers_count=blockers_count,
            asset_blockers=asset_blockers,
            update_status=update_status_payload,
            basket=basket_summary,
            observation_candidates=observation_candidates,
            position_actions=position_actions,
            market_context=context_payload,
        )
        write_daily_report_json(
            report,
            run_path / "report.json",
            prediction=prediction_payload,
            blockers_count=blockers_count,
            asset_blockers=asset_blockers,
            update_status=update_status_payload,
            basket=basket_summary,
            observation_candidates=observation_candidates,
            position_actions=position_actions,
            market_context=context_payload,
        )

    except Exception as exc:
        return {
            "command": "run",
            "profile": normalized_profile,
            "list": list_name.upper(),
            "status": "FAIL",
            "reason": str(exc),
            "files": files,
        }

    ready = _count_status(report, ExecutionStatus.READY)
    watch = _count_status(report, ExecutionStatus.WATCH)
    blocked = _count_status(report, ExecutionStatus.BLOCKED)

    return {
        "command": "run",
        "profile": normalized_profile,
        "list": list_name.upper(),
        "status": "OK",
        "market": {
            "regime": report.market_regime.regime.value,
            "context": context,
            "context_summary": context_payload.get("regime_summary", {}),
            "sector_context": context_payload.get("sector_context", {}),
            "schema_version": context_payload.get("schema_version", ""),
            "update_status": update_status_payload,
        },
        "prediction": prediction_payload,
        "blockers": blockers_count,
        "decision": {
            "actionable": ready,
            "watch": watch,
            "blocked": blocked,
            "rejected": 0,
        },
        "top": _top_rows_with_prediction(
            report,
            min(5, max(1, limit)),
            prediction_payload,
        ),
        "files": files,
        "basket": basket_summary,
        "observation_candidates": observation_candidates,
        "position_actions": position_actions,
        "exit_book": position_actions.get("exit_book", {}),
        "short_candidates": position_actions.get("short_candidates", []),
        "hedge_candidates": position_actions.get("hedge_candidates", []),
        "report": daily_report_to_dict(
            report,
            prediction=prediction_payload,
            blockers_count=blockers_count,
            asset_blockers=asset_blockers,
            update_status=update_status_payload,
            basket=basket_summary,
            observation_candidates=observation_candidates,
            position_actions=position_actions,
            market_context=context_payload,
        ),
    }


def render_run_summary(payload: dict[str, Any]) -> str:
    status = payload.get("status", "-")
    lines = [
        (
            f"RUN | STATUS {colorize(status, status)} | "
            f"PROFILE {payload.get('profile', '-')} | LIST {payload.get('list', '-')}"
        )
    ]

    if status != "OK":
        lines.extend(
            [
                muted_line(),
                f"reason             {payload.get('reason', '-')}",
            ]
        )
        return "\n".join(lines)

    market = payload["market"]
    context_summary = market.get("context_summary", {})
    if not isinstance(context_summary, dict):
        context_summary = {}
    sector_context = market.get("sector_context", {})
    if not isinstance(sector_context, dict):
        sector_context = {}
    update_status = market.get("update_status", {})
    update_freshness = update_status.get("freshness", {})
    if not isinstance(update_freshness, dict):
        update_freshness = {}
    prediction = payload.get("prediction", {})
    model_quality = prediction.get("model_quality", {})
    decision = payload["decision"]
    blockers = payload.get("blockers", {})
    files = payload["files"]
    horizons = prediction.get("horizons", [])
    horizon_text = ",".join(f"D{item}" for item in horizons) if horizons else "-"
    weights_text = format_observer_weights(prediction.get("weights", {}))
    lines.extend(
        [
            "",
            format_kv_section(
                "MARKET",
                [
                    ("regime", market["regime"], market["regime"]),
                    ("trend", context_summary.get("market_trend", "-")),
                    ("volatility", context_summary.get("market_volatility", "-")),
                    ("context_score", context_summary.get("context_score", "-")),
                    (
                        "context_quality",
                        context_summary.get("context_quality", "-"),
                        context_summary.get("context_quality", "-"),
                    ),
                    (
                        "main_drivers",
                        ", ".join(context_summary.get("main_drivers", []) or []),
                    ),
                    (
                        "main_risks",
                        ", ".join(context_summary.get("main_risks", []) or []),
                    ),
                    (
                        "update_status",
                        update_status.get("status", "-"),
                        update_status.get("status", "-"),
                    ),
                    (
                        "impact",
                        update_status.get("impact", "-"),
                        update_status.get("impact", "-"),
                    ),
                    (
                        "regime_reliability",
                        update_status.get("regime_reliability", "-"),
                        update_status.get("regime_reliability", "-"),
                    ),
                    (
                        "freshness",
                        update_freshness.get("freshness_status", "-"),
                        update_freshness.get("freshness_status", "-"),
                    ),
                    ("max_staleness", f"{update_freshness.get('max_staleness_days', 0)}d"),
                    ("data_quality", update_freshness.get("data_quality_score", "-")),
                ],
            ),
            "",
            format_kv_section(
                "PREDICTION",
                [
                    ("engine", prediction.get("engine_used", "-")),
                    ("horizons", horizon_text),
                    ("observer", prediction.get("observer_mode", "-")),
                    ("weights", weights_text),
                    ("combined_score", prediction.get("combined_score", "-")),
                    (
                        "behavior",
                        prediction.get("behavior", "-"),
                        prediction.get("behavior", "-"),
                    ),
                    ("dominant", prediction.get("dominant_horizon", "-")),
                    (
                        "alignment",
                        prediction.get("horizon_alignment", "-"),
                        prediction.get("horizon_alignment", "-"),
                    ),
                    (
                        "dominance",
                        prediction.get("dominance_strength", "-"),
                        prediction.get("dominance_strength", "-"),
                    ),
                ],
            ),
            "",
            format_kv_section(
                "MODEL QUALITY",
                [
                    (
                        "status",
                        model_quality.get("status", "-"),
                        model_quality.get("status", "-"),
                    ),
                    ("edge", model_quality.get("edge", "-")),
                ],
            ),
            "",
            format_kv_section(
                "DECISION",
                [
                    ("actionable", decision["actionable"], "ACTIONABLE"),
                    ("watch", decision["watch"], "WATCH"),
                    ("blocked", decision["blocked"], "BLOCKED"),
                    ("rejected", decision["rejected"], "REJECTED"),
                ],
            ),
            "",
        ]
    )

    if sector_context:
        lines.extend(["", "SECTOR CONTEXT", muted_line()])
        for sector, item in list(sector_context.items())[:8]:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"{sector:<22} {str(item.get('context', '-')):<10} "
                f"{str(item.get('reason', '-'))}"
            )

    if blockers:
        blocker_rows = [
            (reason, count, reason)
            for reason, count in blockers.items()
        ]
        lines.append(format_kv_section("BLOCKERS", blocker_rows, label_width=20))
    else:
        lines.append(format_kv_section("BLOCKERS", [("none", 0)], label_width=20))

    top_rows = payload.get("top", [])
    lines.extend(
        [
            "",
            "TOP",
            muted_line(),
            (
                f"{'#':>2} {'TICKER':<8} {'STATUS':<10} {'SCORE':>8} "
                f"{'REASONS':<{TOP_REASONS_WIDTH}} {'BEHAVIOR':<14} "
                f"{'DOM':<4} {'ALIGN':<14}"
            ),
        ]
    )

    legend_codes: list[str] = []
    if not top_rows:
        lines.append("No rows.")
    for index, item in enumerate(top_rows, start=1):
        behavior = str(item.get("behavior", "-") or "-")
        dominant = str(item.get("dominant_horizon", "-") or "-")
        alignment = str(item.get("horizon_alignment", "-") or "-")
        status_text = colorize(f"{item['decision']:<10}", item["decision"])
        reasons, used_codes = format_top_reasons(item)
        legend_codes.extend(used_codes)
        lines.append(
            f"{index:>2} {item['ticker']:<8} {status_text} "
            f"{float(item['score']):>8.2f} "
            f"{reasons:<{TOP_REASONS_WIDTH}} "
            f"{truncate(behavior, 14):<14} "
            f"{truncate(dominant, 4):<4} "
            f"{truncate(alignment, 14):<14}"
        )
    legend = format_top_reason_legend(legend_codes)
    if legend:
        lines.extend(["", "LEGEND", legend])

    observation_candidates = payload.get("observation_candidates", [])
    if decision.get("actionable", 0) == 0 and observation_candidates:
        lines.extend(["", *render_observation_candidates(observation_candidates)])

    position_actions = payload.get("position_actions", {})
    if position_actions:
        lines.extend(["", *render_position_books(position_actions)])

    lines.extend(
        [
            "",
            format_kv_section(
                "FILES",
                [
                    ("report", files["report"]),
                    ("json", files["json"]),
                    ("run_dir", files["run_dir"]),
                ],
            ),
        ]
    )

    if payload.get("basket"):
        basket = payload["basket"]
        basket_rows = [
            ("status", basket["status"], basket["status"]),
            ("slots", basket["slots"]),
            ("assets", basket["assets"]),
        ]
        if basket.get("reason"):
            basket_rows.append(("reason", basket["reason"]))
        if basket.get("status") != "BLOCKED":
            basket_rows.append(("output", basket["output"]))
        lines.extend(["", format_kv_section("BASKET", basket_rows)])

    return "\n".join(lines)


def run_run_command(args: Any) -> int:
    payload = run_decision_flow(
        profile=args.profile,
        list_name=args.list,
        policy=args.policy,
        universe=args.universe,
        context=args.context,
        matrix=args.matrix,
        evaluation=args.evaluation,
        observation_config=args.observation_config,
        positions=args.positions,
        borrow_data=getattr(args, "borrow_data", "storage/borrow/latest_borrow_data.csv"),
        prices_dir=args.prices_dir,
        limit=args.limit,
        run_dir=args.run_dir,
        report_output=args.report_output,
        json_output=args.json_output,
        basket=args.basket,
        slots=args.slots,
        min_sectors=args.min_sectors,
        min_weight=args.min_weight,
        capital=args.capital,
        risk_per_trade=args.risk_per_trade,
        targets=args.targets,
        stop=args.stop,
        basket_output=args.basket_output,
        allow_experimental_model=getattr(args, "allow_experimental_model", False),
    )

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_run_summary(payload))

    return 0 if payload["status"] == "OK" else 1
