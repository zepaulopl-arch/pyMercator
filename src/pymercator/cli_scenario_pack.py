from __future__ import annotations

from typing import Any

from pymercator.scenario_pack import run_scenario_pack


def run_scenario_pack_command(args: Any) -> int:
    context_values = args.context_values

    pack_dir, summary_text, stability_text = run_scenario_pack(
        universe_path=args.universe,
        universe_name=args.universe_name,
        headline_tags=context_values["headline_tags"],
        market_trend=context_values["market_trend"],
        market_volatility=context_values["market_volatility"],
        policy_path=args.policy,
        run_dir=args.run_dir,
        limit=args.limit,
    )

    print(summary_text)
    print("")
    print(stability_text)
    print("")
    print(f"PACK DIR             {pack_dir}")

    return 0
