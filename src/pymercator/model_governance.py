from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

from pymercator.domain import DailyReport, ExecutionStatus
from pymercator.explain import decision_codes

STATUS_ONLY_CODES = {"OK", "CAUTION", "BLOCKED", "UNKNOWN"}
GLOBAL_BLOCKER_PRIORITY = (
    "MODEL_WEAK",
    "RISK_OFF",
    "BEHAVIOR_AVOID",
    "REGIME_DENY",
    "VOL_HIGH",
)
BLOCKING_MODEL_QUALITY = {"WEAK", "DEGENERATE"}


def dedupe(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item for item in values if item))


def model_quality_status(prediction: dict[str, Any]) -> str:
    quality = prediction.get("model_quality", {})
    if not isinstance(quality, dict):
        return ""
    return str(quality.get("status", "")).strip().upper()


def prediction_behavior(prediction: dict[str, Any]) -> str:
    return str(prediction.get("behavior", "")).strip().upper()


def load_model_quality_governance(policy: str) -> dict[str, Any]:
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


def global_blockers(report: DailyReport, prediction: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if model_quality_status(prediction) in BLOCKING_MODEL_QUALITY:
        blockers.append("MODEL_WEAK")
    if report.market_regime.regime.value == "RISK_OFF":
        blockers.append("RISK_OFF")
    if prediction_behavior(prediction) == "AVOID":
        blockers.append("BEHAVIOR_AVOID")
    return list(dedupe(tuple(blockers)))


def ordered_blockers(codes: list[str]) -> list[str]:
    priority = {code: index for index, code in enumerate(GLOBAL_BLOCKER_PRIORITY)}
    unique = list(dedupe(tuple(codes)))
    return sorted(unique, key=lambda code: (priority.get(code, 999), code))


def blockers_for_decision(
    decision: Any,
    report: DailyReport,
    prediction: dict[str, Any],
) -> list[str]:
    codes = global_blockers(report, prediction)
    codes.extend(code for code in decision_codes(decision) if code not in STATUS_ONLY_CODES)
    return ordered_blockers(codes)


def asset_blockers(
    report: DailyReport,
    prediction: dict[str, Any],
) -> dict[str, list[str]]:
    return {
        decision.asset.ticker: blockers_for_decision(decision, report, prediction)
        for decision in report.decisions
    }


def blocker_counts(blockers_by_asset: dict[str, list[str]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for blockers in blockers_by_asset.values():
        counts.update(blockers)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def apply_model_quality_guard(
    report: DailyReport,
    prediction: dict[str, Any],
    policy: str,
) -> DailyReport:
    quality_status = model_quality_status(prediction)
    if quality_status not in BLOCKING_MODEL_QUALITY:
        return report

    governance = load_model_quality_governance(policy)
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
            reasons=dedupe((*decision.permission.reasons, reason)),
        )
        decisions.append(replace(decision, permission=permission))

    return replace(
        report,
        decisions=tuple(decisions),
        posture="STAND_ASIDE",
        reasons=dedupe((*report.reasons, f"{reason}; operations blocked")),
    )


def apply_prediction_behavior_guard(
    report: DailyReport,
    prediction: dict[str, Any],
) -> DailyReport:
    if prediction_behavior(prediction) != "AVOID":
        return report

    reason = "BEHAVIOR_AVOID: behavior is AVOID"
    decisions = []
    for decision in report.decisions:
        permission = replace(
            decision.permission,
            status=ExecutionStatus.BLOCKED,
            max_position_factor=0.0,
            reasons=dedupe((*decision.permission.reasons, reason)),
        )
        decisions.append(replace(decision, permission=permission))

    return replace(
        report,
        decisions=tuple(decisions),
        posture="STAND_ASIDE",
        reasons=dedupe((*report.reasons, f"{reason}; operations blocked")),
    )
