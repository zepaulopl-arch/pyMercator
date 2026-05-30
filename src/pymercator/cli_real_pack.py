from __future__ import annotations

import json
from typing import Any

from pymercator.execution_policy import load_execution_policy
from pymercator.real_run import run_real_pack


def run_real_pack_command(args: Any) -> int:
    context_values = args.context_values
    execution_policy = load_execution_policy(args.execution_policy)

    payload = run_real_pack(
        tickers_file=args.tickers_file,
        features_file=getattr(args, "features_file", "config/features_catalog.json"),
        start=args.start,
        end=args.end or None,
        prices_dir=args.prices_dir,
        universe_output=args.universe_output,
        run_dir=args.run_dir,
        headline_tags=context_values["headline_tags"],
        universe_name=args.universe_name,
        market_trend=context_values["market_trend"],
        market_volatility=context_values["market_volatility"],
        policy_path=args.policy,
        limit=args.limit,
        skip_fetch=args.skip_fetch,
        context_source=context_values["context_source"],
        context_file=context_values["context_file"],
        context_preset=context_values["context_preset"],
        context_notes=context_values["context_notes"],
        context_snapshot=context_values["context_snapshot"],
        execution_mode=execution_policy["execution_mode"],
        allow_order_routing=execution_policy["allow_order_routing"],
        require_human_confirmation=execution_policy["require_human_confirmation"],
    )

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload["summary_text"])

    return 0 if payload["status"] == "OK" else 1
