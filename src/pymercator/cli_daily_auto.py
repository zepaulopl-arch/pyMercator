from __future__ import annotations

import json
from typing import Any

from pymercator.cli_args import parse_csv_arg
from pymercator.daily_auto import render_daily_auto_summary, run_daily_auto
from pymercator.execution_policy import load_execution_policy


def run_daily_auto_command(args: Any) -> int:
    execution_policy = load_execution_policy(args.execution_policy)

    payload = run_daily_auto(
        indices_catalog=args.indices_catalog,
        indices_start=args.indices_start,
        indices_dir=args.indices_dir,
        context_output=args.context_output,
        features_file=args.features_file,
        feature_matrix_output=args.feature_matrix_output,
        prediction_dataset_output=args.prediction_dataset_output,
        prediction_evaluation_output=args.prediction_evaluation_output,
        prediction_horizon=args.prediction_horizon,
        prediction_min_history=args.prediction_min_history,
        prediction_min_train_rows=args.prediction_min_train_rows,
        prediction_engines=parse_csv_arg(args.prediction_engines),
        prediction_n_jobs=args.prediction_n_jobs,
        prediction_autotune=args.prediction_autotune,
        prediction_autotune_iter=args.prediction_autotune_iter,
        prediction_autotune_cv=args.prediction_autotune_cv,
        tickers_file=args.tickers_file,
        sentiment_dir=args.sentiment_dir,
        prices_start=args.prices_start,
        prices_dir=args.prices_dir,
        universe_output=args.universe_output,
        run_dir=args.run_dir,
        universe_name=args.universe_name,
        policy_path=args.policy,
        execution_mode=execution_policy["execution_mode"],
        allow_order_routing=execution_policy["allow_order_routing"],
        require_human_confirmation=execution_policy["require_human_confirmation"],
        skip_asset_fetch=args.skip_asset_fetch,
        fetch_indices=not args.skip_indices_fetch,
    )

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_daily_auto_summary(payload))

    return 0 if payload["status"] == "OK" else 1
