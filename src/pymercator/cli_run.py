from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pymercator.basket import run_daily_basket
from pymercator.domain import DailyReport, ExecutionStatus
from pymercator.explain import decision_label
from pymercator.market_context import load_market_context
from pymercator.pipeline import run_daily_pipeline
from pymercator.policy import normalize_profile
from pymercator.reports.json_report import daily_report_to_dict, write_daily_report_json
from pymercator.reports.terminal import render_daily_report


def _count_status(report: DailyReport, status: ExecutionStatus) -> int:
    return sum(1 for item in report.decisions if item.permission.status == status)


def _tickers_by_status(report: DailyReport, status: ExecutionStatus) -> list[str]:
    return [
        item.asset.ticker
        for item in report.decisions
        if item.permission.status == status
    ]


def _top_rows(report: DailyReport, limit: int = 5) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in report.decisions[:limit]:
        rows.append(
            {
                "ticker": item.asset.ticker,
                "decision": item.permission.status.value,
                "score": item.ranking.context_score,
                "guard": decision_label(item),
            }
        )
    return rows


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
        }

    observer = payload.get("horizon_observer", {})
    if not isinstance(observer, dict):
        observer = {}

    scores = observer.get("scores", {})
    if not isinstance(scores, dict):
        scores = {}

    return {
        "engine_used": "multi_horizon_ridge",
        "is_baseline": False,
        "horizons": payload.get("horizons", []),
        "observer_mode": observer.get("mode", payload.get("observer", {}).get("mode", "-")),
        "d5_score": scores.get("D5"),
        "d20_score": scores.get("D20"),
        "d60_score": scores.get("D60"),
        "combined_score": observer.get("combined_score"),
        "dominant_horizon": observer.get("dominant_horizon"),
        "behavior": observer.get("behavior"),
        "source": path,
    }


def _top_rows_with_prediction(
    report: DailyReport,
    limit: int,
    prediction: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = _top_rows(report, limit)
    if not prediction or prediction.get("engine_used") != "multi_horizon_ridge":
        return rows

    prediction_fields = {
        "d5_score": prediction.get("d5_score"),
        "d20_score": prediction.get("d20_score"),
        "d60_score": prediction.get("d60_score"),
        "combined_score": prediction.get("combined_score"),
        "dominant_horizon": prediction.get("dominant_horizon"),
        "behavior": prediction.get("behavior"),
    }
    for row in rows:
        row.update(prediction_fields)
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

    prediction_payload = _load_prediction_observer(evaluation)

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

        rendered = render_daily_report(report, limit=limit)
        report_path = Path(report_output)
        json_path = Path(json_output)
        run_path = Path(run_dir)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        run_path.mkdir(parents=True, exist_ok=True)

        report_path.write_text(rendered, encoding="utf-8")
        write_daily_report_json(report, json_path)
        (run_path / "report.txt").write_text(rendered, encoding="utf-8")
        write_daily_report_json(report, run_path / "report.json")

        ready_tickers = _tickers_by_status(report, ExecutionStatus.READY)
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
                blocked_reason="no actionable assets",
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
    basket_summary = None
    if basket_payload is not None:
        basket_summary = {
            "status": basket_payload.get("status", "-"),
            "slots": basket_payload.get("slots", slots),
            "assets": len(basket_payload.get("rows", [])),
            "reason": basket_payload.get("reason", ""),
            "output": basket_payload.get("output_csv", basket_output),
        }

    return {
        "command": "run",
        "profile": normalized_profile,
        "list": list_name.upper(),
        "status": "OK",
        "market": {
            "regime": report.market_regime.regime.value,
            "context": context,
        },
        "prediction": prediction_payload,
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
        "report": daily_report_to_dict(report),
    }


def render_run_summary(payload: dict[str, Any]) -> str:
    status = payload.get("status", "-")
    lines = [
        (
            f"RUN | STATUS {status} | PROFILE {payload.get('profile', '-')} | "
            f"LIST {payload.get('list', '-')}"
        )
    ]

    if status != "OK":
        lines.append(f"REASON: {payload.get('reason', '-')}")
        return "\n".join(lines)

    market = payload["market"]
    prediction = payload.get("prediction", {})
    decision = payload["decision"]
    files = payload["files"]
    lines.extend(
        [
            "",
            "MARKET:",
            f"- regime: {market['regime']}",
            f"- context: {market['context']}",
            "",
            "PREDICTION:",
            f"- engine: {prediction.get('engine_used', '-')}",
            f"- horizons: {prediction.get('horizons', [])}",
            f"- combined_score: {prediction.get('combined_score', '-')}",
            f"- dominant_horizon: {prediction.get('dominant_horizon', '-')}",
            f"- behavior: {prediction.get('behavior', '-')}",
            "",
            "DECISION:",
            f"- actionable: {decision['actionable']}",
            f"- watch: {decision['watch']}",
            f"- blocked: {decision['blocked']}",
            f"- rejected: {decision['rejected']}",
            "",
            "TOP:",
        ]
    )

    for index, item in enumerate(payload.get("top", []), start=1):
        observer_note = ""
        if item.get("dominant_horizon") and item.get("behavior"):
            observer_note = f" | {item['dominant_horizon']} {item['behavior']}"
        lines.append(
            f"{index}. {item['ticker']} | {item['decision']} | "
            f"{item['score']} | {item['guard']}{observer_note}"
        )

    lines.extend(
        [
            "",
            "FILES:",
            f"- report: {files['report']}",
            f"- json: {files['json']}",
            f"- run_dir: {files['run_dir']}",
        ]
    )

    if payload.get("basket"):
        basket = payload["basket"]
        lines.extend(
            [
                "",
                "BASKET:",
                f"- status: {basket['status']}",
                f"- slots: {basket['slots']}",
                f"- assets: {basket['assets']}",
            ]
        )
        if basket.get("reason"):
            lines.append(f"- reason: {basket['reason']}")
        if basket.get("status") != "BLOCKED":
            lines.append(f"- output: {basket['output']}")

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
    )

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_run_summary(payload))

    return 0 if payload["status"] == "OK" else 1
