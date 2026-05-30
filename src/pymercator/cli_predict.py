from __future__ import annotations

import json
from typing import Any

from pymercator.prediction_lab import (
    render_evaluation_summary,
    render_prediction_dataset_summary,
    render_prediction_lab_summary,
    run_prediction_lab,
    write_evaluation_report,
    write_prediction_dataset,
)


def run_predict_command(args: Any) -> int:
    if args.predict_command == "dataset":
        payload = write_prediction_dataset(
            matrix=args.matrix,
            prices_dir=args.prices_dir,
            output=args.output,
            horizon=args.horizon,
            min_history=args.min_history,
        )

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_prediction_dataset_summary(payload))

        return 0

    if args.predict_command == "evaluate":
        payload = write_evaluation_report(
            dataset=args.dataset,
            output=args.output,
            horizon=args.horizon,
            min_train_rows=args.min_train_rows,
            engines=_parse_csv_arg(args.engines),
            n_jobs=args.n_jobs,
            autotune=args.autotune,
            autotune_iter=args.autotune_iter,
            autotune_cv=args.autotune_cv,
        )

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_evaluation_summary(payload))

        return 0

    if args.predict_command == "lab":
        payload = run_prediction_lab(
            matrix=args.matrix,
            prices_dir=args.prices_dir,
            dataset_output=args.dataset_output,
            evaluation_output=args.evaluation_output,
            horizon=args.horizon,
            min_history=args.min_history,
            min_train_rows=args.min_train_rows,
            engines=_parse_csv_arg(args.engines),
            n_jobs=args.n_jobs,
            autotune=args.autotune,
            autotune_iter=args.autotune_iter,
            autotune_cv=args.autotune_cv,
        )

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_prediction_lab_summary(payload))

        return 0

    raise ValueError(f"Unknown predict command: {args.predict_command}")


def _parse_csv_arg(value: str) -> list[str]:
    return [
        item.strip()
        for item in str(value or "").split(",")
        if item.strip()
    ]
