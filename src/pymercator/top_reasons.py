from __future__ import annotations

from typing import Any

TOP_REASONS_WIDTH = 20

REASON_ABBREVIATIONS = {
    "MODEL_WEAK": "MW",
    "RISK_OFF": "RO",
    "BEHAVIOR_AVOID": "AVOID",
    "VOL_HIGH": "VOL",
    "ATR_HIGH": "ATR",
    "MODEL_STRONG": "MS",
    "RISK_ON": "RON",
    "TREND_CONFIRM": "TC",
    "WATCH": "W",
    "BLOCKED": "B",
}

REASON_LEGEND = {
    "MW": "model weak",
    "RO": "risk off",
    "AVOID": "behavior avoid",
    "VOL": "volatility high",
    "ATR": "ATR high",
    "MS": "model strong",
    "RON": "risk on",
    "TC": "trend confirm",
    "W": "watch",
    "B": "blocked",
}


def top_reason_tokens(item: dict[str, Any]) -> list[str]:
    blockers = item.get("blockers", [])
    if isinstance(blockers, list) and blockers:
        return [str(token).strip() for token in blockers if str(token).strip()]

    guard = str(item.get("guard", "") or "").strip()
    if not guard:
        return []
    return [token.strip() for token in guard.split("+") if token.strip()]


def format_top_reasons(
    item: dict[str, Any],
    *,
    width: int = TOP_REASONS_WIDTH,
) -> tuple[str, list[str]]:
    tokens = top_reason_tokens(item)
    if not tokens:
        return "-", []

    codes: list[str] = []
    legend_codes: list[str] = []
    for token in tokens:
        normalized = token.split(":", 1)[0].strip().upper()
        code = REASON_ABBREVIATIONS.get(normalized, normalized)
        codes.append(code)
        if normalized in REASON_ABBREVIATIONS and code in REASON_LEGEND:
            legend_codes.append(code)

    selected: list[str] = []
    for index, code in enumerate(codes):
        remaining = len(codes) - index - 1
        candidate_codes = [*selected, code]
        suffix = f"+{remaining}" if remaining else ""
        candidate = "+".join(candidate_codes) + suffix
        if len(candidate) <= width or not selected:
            selected.append(code)
            continue
        break

    omitted = len(codes) - len(selected)
    display = "+".join(selected)
    if omitted:
        display = f"{display}+{omitted}" if display else f"+{omitted}"

    used_legend_codes = [code for code in selected if code in legend_codes]
    return display, used_legend_codes


def format_top_reason_legend(codes: list[str]) -> str:
    ordered = list(dict.fromkeys(code for code in codes if code in REASON_LEGEND))
    return " | ".join(f"{code}={REASON_LEGEND[code]}" for code in ordered)
