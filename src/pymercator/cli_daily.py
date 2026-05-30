from __future__ import annotations

from pathlib import Path
from typing import Any

from pymercator.pipeline import run_daily_pipeline
from pymercator.reports.json_report import write_daily_report_json
from pymercator.reports.terminal import render_daily_report


def run_daily_command(
    *,
    args: Any,
    resolved_output: str,
    json_output: str,
    resolved_run_dir: str,
    context_values: dict[str, Any],
) -> int:
    report = run_daily_pipeline(
        universe_path=args.universe,
        universe_name=args.universe_name,
        profile=args.profile,
        headline_risk=args.headline_risk,
        headline_tags=context_values["headline_tags"],
        market_trend=context_values["market_trend"],
        market_volatility=context_values["market_volatility"],
        policy_path=args.policy,
    )

    rendered = render_daily_report(report, limit=args.limit)

    if resolved_output:
        # write resolved_output created by caller
        Path(resolved_output).parent.mkdir(parents=True, exist_ok=True)
        Path(resolved_output).write_text(rendered, encoding="utf-8")

    if json_output:
        write_daily_report_json(report, json_output)

    print(rendered)

    if resolved_run_dir:
        print("")
        print(f"RUN DIR              {resolved_run_dir}")

    return 0
