from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PATHS = {
    "train_audit": Path("storage/training/latest_train_audit.json"),
    "engine_scoreboard": Path("storage/reports/latest_engine_scoreboard.json"),
    "daily_report": Path("storage/reports/latest_daily_report.json"),
    "feature_audit": Path("storage/features/latest_feature_audit.json"),
    "canonical_features": Path("storage/features/latest_canonical_features.json"),
    "multi_horizon": Path("storage/prediction/latest_multi_horizon_evaluation.json"),
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _upper(value: Any, default: str = "-") -> str:
    raw = str(value if value is not None else default).strip()
    return raw.upper() if raw else default


def _feature_status(feature_audit: dict[str, Any], canonical: dict[str, Any]) -> str:
    if not feature_audit:
        return "MISSING"

    unknown = int(_to_float(feature_audit.get("unknown_group_features"), 0))
    missing_rate = _to_float(feature_audit.get("missing_rate"), 0.0)
    constants = int(_to_float(feature_audit.get("constant_features"), 0))
    corr = int(_to_float(feature_audit.get("high_corr_pairs"), 0))

    canonical_count = int(_to_float(canonical.get("canonical_features"), 0))
    raw_count = int(_to_float(canonical.get("total_input_features"), 0))

    if unknown > 0:
        return "WARNING"

    if missing_rate > 0.05:
        return "WARNING"

    if canonical_count <= 0:
        return "MISSING"

    if constants > 0 or corr > 0 or canonical_count < raw_count:
        return "OK_WITH_WARNINGS"

    return "OK"


def _engine_status(scoreboard: dict[str, Any]) -> str:
    if not scoreboard:
        return "MISSING"

    best = scoreboard.get("best_engine")
    least_bad = scoreboard.get("least_bad_engine")
    hurting = scoreboard.get("hurting_engines") or []

    horizon_quality = scoreboard.get("horizon_quality") or {}
    d60 = horizon_quality.get("D60", {})
    d20 = horizon_quality.get("D20", {})

    d60_edge = _to_float(d60.get("edge"), 0.0) if isinstance(d60, dict) else 0.0
    d20_edge = _to_float(d20.get("edge"), 0.0) if isinstance(d20, dict) else 0.0

    if best:
        if hurting:
            return "MIXED"
        return "OK"

    if least_bad and d60_edge > 0 and d20_edge < 0:
        return "WEAK_D60_ONLY"

    if least_bad:
        return "WEAK"

    return "WEAK"


def _train_status(train: dict[str, Any]) -> str:
    if not train:
        return "MISSING"

    status = _upper(train.get("status"))
    verdict = _upper(train.get("verdict"))
    quality = _upper(train.get("quality"))
    edge = _to_float(train.get("edge"), 0.0)

    if status == "OPERABLE" and edge > 0 and verdict not in {"D60_ONLY", "WEAK"}:
        return "OK"

    if status == "OBSERVABLE" and verdict == "D60_ONLY":
        return "OBSERVABLE_D60_ONLY"

    if quality == "WEAK" or edge <= 0:
        return "WEAK"

    return status


def _context_status(daily: dict[str, Any]) -> str:
    if not daily:
        return "MISSING"

    # Try common locations from existing daily report.
    context = daily.get("context")
    market = daily.get("market")
    if not isinstance(context, dict):
        context = {}
    if not isinstance(market, dict):
        market = {}

    quality = _upper(
        context.get("context_quality")
        or context.get("quality")
        or market.get("context_quality")
        or daily.get("context_quality")
        or "-"
    )

    update_status = _upper(
        context.get("update_status")
        or market.get("update_status")
        or daily.get("update_status")
        or "-"
    )

    if quality in {"OK", "GOOD", "COMPLETE"} and update_status in {"OK", "GOOD", "-"}:
        return "OK"

    if quality in {"PARTIAL", "-", "UNKNOWN"} or update_status in {"PARTIAL", "-", "UNKNOWN"}:
        return "PARTIAL"

    return "WARNING"


def _signal_status(daily: dict[str, Any], train: dict[str, Any]) -> str:
    if not daily:
        return "MISSING"

    decision = daily.get("decision")
    basket = daily.get("basket")
    if not isinstance(decision, dict):
        decision = {}
    if not isinstance(basket, dict):
        basket = {}

    actionable = int(_to_float(decision.get("actionable"), 0))
    blocked = int(_to_float(decision.get("blocked"), 0))
    basket_status = _upper(basket.get("status"))

    train_status = _upper(train.get("status"))
    train_verdict = _upper(train.get("verdict"))

    if actionable > 0 and train_status == "OPERABLE" and train_verdict not in {"D60_ONLY", "WEAK"}:
        return "ACTIONABLE_WITH_GATES"

    if basket_status == "BLOCKED" or actionable == 0 or blocked > 0:
        return "OBSERVATION_ONLY"

    return "OBSERVATION_ONLY"


def _short_status(daily: dict[str, Any]) -> str:
    if not daily:
        return "UNKNOWN"

    text = json.dumps(daily, ensure_ascii=False).upper()

    if "BORROW_DATA_MISSING" in text or "BORROW/COST UNAVAILABLE" in text:
        return "COST_RR_BLOCKED"

    if "SHORT_BLOCKED" in text or "MANUAL_BLOCK" in text:
        return "MANUAL_ONLY"

    if "SHORT_SETUP" in text:
        return "MANUAL_ONLY"

    return "INACTIVE"


def _review_status() -> str:
    # Etapa 8 nÃ£o deve inventar review. Se nÃ£o houver artefato claro, fica PARTIAL.
    candidates = [
        Path("storage/reports/latest_review.json"),
        Path("storage/reports/latest_observation_review.json"),
        Path("storage/reports/latest_review_report.json"),
    ]

    for p in candidates:
        if p.exists():
            data = _read_json(p)
            status = _upper(data.get("status"), "OK")
            if status in {"OK", "GOOD"}:
                return "OK"
            return status

    return "PARTIAL"


def _data_status(feature_status: str, context_status: str, daily: dict[str, Any]) -> str:
    if not daily:
        return "WARNING"

    data_quality = None

    for key in ("data_quality", "quality"):
        if key in daily:
            data_quality = daily.get(key)

    market = daily.get("market")
    if isinstance(market, dict):
        data_quality = market.get("data_quality", data_quality)

    dq = _to_float(data_quality, -1)

    if feature_status == "MISSING":
        return "WARNING"

    if context_status in {"MISSING", "WARNING"}:
        return "WARNING"

    if dq >= 95:
        return "OK"

    if dq >= 0:
        return "WARNING"

    return "WARNING"


def _overall_trust(statuses: dict[str, str]) -> str:
    severe = {"MISSING"}
    bad = {"WEAK", "WARNING", "COST_RR_BLOCKED"}
    partial = {"PARTIAL", "OBSERVATION_ONLY", "OBSERVABLE_D60_ONLY", "WEAK_D60_ONLY", "OK_WITH_WARNINGS", "MANUAL_ONLY"}

    values = set(statuses.values())

    if values & severe:
        return "LOW"

    if statuses.get("signal_status") == "ACTIONABLE_WITH_GATES" and statuses.get("train_status") == "OK":
        if statuses.get("engine_status") in {"OK", "MIXED"} and statuses.get("data_status") == "OK":
            return "MEDIUM_HIGH"

    if statuses.get("train_status") == "OBSERVABLE_D60_ONLY":
        return "MEDIUM_LOW"

    if values & bad:
        return "LOW"

    if values & partial:
        return "MEDIUM_LOW"

    return "MEDIUM"


def build_trust_report() -> dict[str, Any]:
    train = _read_json(PATHS["train_audit"])
    engines = _read_json(PATHS["engine_scoreboard"])
    daily = _read_json(PATHS["daily_report"])
    feature_audit = _read_json(PATHS["feature_audit"])
    canonical = _read_json(PATHS["canonical_features"])
    multi = _read_json(PATHS["multi_horizon"])

    context_status = _context_status(daily)
    features_status = _feature_status(feature_audit, canonical)
    engine_status = _engine_status(engines)
    train_status = _train_status(train)
    signal_status = _signal_status(daily, train)
    short_status = _short_status(daily)
    review_status = _review_status()
    data_status = _data_status(features_status, context_status, daily)

    statuses = {
        "context_status": context_status,
        "features_status": features_status,
        "engine_status": engine_status,
        "train_status": train_status,
        "signal_status": signal_status,
        "short_status": short_status,
        "review_status": review_status,
        "data_status": data_status,
    }

    overall = _overall_trust(statuses)

    verdict_lines = _verdict_lines(statuses, train, engines, daily, multi)

    result = {
        **statuses,
        "overall_trust": overall,
        "verdict": verdict_lines,
        "sources": {key: str(path) for key, path in PATHS.items()},
    }

    Path("storage/reports").mkdir(parents=True, exist_ok=True)
    Path("storage/reports/latest_trust_report.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return result


def _verdict_lines(
    statuses: dict[str, str],
    train: dict[str, Any],
    engines: dict[str, Any],
    daily: dict[str, Any],
    multi: dict[str, Any],
) -> list[str]:
    lines: list[str] = []

    train_status = statuses.get("train_status")
    signal_status = statuses.get("signal_status")
    short_status = statuses.get("short_status")
    engine_status = statuses.get("engine_status")
    features_status = statuses.get("features_status")
    data_status = statuses.get("data_status")

    if signal_status == "ACTIONABLE_WITH_GATES":
        lines.append("Use only with policy gates and regime confirmation.")
    else:
        lines.append("Use for observation.")

    lines.append("Do not automate execution.")

    if train_status == "OBSERVABLE_D60_ONLY":
        lines.append("Train improved, but trust is concentrated in D60.")
    elif train_status == "WEAK":
        lines.append("Train quality is still weak.")
    elif train_status == "OK":
        lines.append("Train quality is acceptable, but still requires operational gates.")

    if engine_status in {"WEAK", "WEAK_D60_ONLY"}:
        least_bad = engines.get("least_bad_engine") if isinstance(engines, dict) else None
        if least_bad:
            lines.append(f"Engines are weak overall; least bad engine is {least_bad}.")
        else:
            lines.append("Engines are weak overall.")

    horizon = engines.get("most_reliable_horizon") if isinstance(engines, dict) else None
    if horizon:
        lines.append(f"Most reliable horizon is {horizon}.")

    if short_status == "COST_RR_BLOCKED":
        lines.append("Short engine active but blocked by borrow/cost availability.")
    elif short_status == "MANUAL_ONLY":
        lines.append("Short engine is manual-only.")

    if features_status == "OK_WITH_WARNINGS":
        lines.append("Features are usable, but audit still has constants/correlations.")

    if data_status != "OK":
        lines.append("Data status is not fully clean; keep warnings visible.")

    return lines


def print_trust_report(result: dict[str, Any]) -> None:
    print("AURUM TRUST REPORT")
    print("-" * 80)

    keys = [
        "context_status",
        "features_status",
        "engine_status",
        "train_status",
        "signal_status",
        "short_status",
        "review_status",
        "data_status",
        "overall_trust",
    ]

    for key in keys:
        print(f"{key:<24} {result.get(key, '-')}")

    print()
    print("VERDICT")
    print("-" * 80)

    for line in result.get("verdict", []):
        print(line)
