from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pymercator.prediction_lab import (
    render_evaluation_summary,
    render_prediction_dataset_summary,
    render_prediction_lab_summary,
    run_prediction_lab,
    write_evaluation_report,
    write_prediction_dataset,
)


def resolve_single_horizon_dataset_output(path: str, horizon: int) -> str:
    output = Path(path)
    if output.name == "latest_dataset.csv" and output.parent.name == "prediction":
        return str(output.parent / f"d{int(horizon)}" / "latest_dataset.csv")
    return str(output)


def resolve_single_horizon_evaluation_output(path: str, horizon: int) -> str:
    output = Path(path)
    if output.name == "latest_evaluation.json" and output.parent.name == "prediction":
        return str(output.parent / f"d{int(horizon)}" / "latest_evaluation.json")
    return str(output)


def run_predict_command(args: Any) -> int:
    if args.predict_command == "dataset":
        output = resolve_single_horizon_dataset_output(args.output, args.horizon)
        payload = write_prediction_dataset(
            matrix=args.matrix,
            prices_dir=args.prices_dir,
            output=output,
            horizon=args.horizon,
            min_history=args.min_history,
        )

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_prediction_dataset_summary(payload))

        return 0

    if args.predict_command == "evaluate":
        output = resolve_single_horizon_evaluation_output(args.output, args.horizon)
        payload = write_evaluation_report(
            dataset=args.dataset,
            output=output,
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
        dataset_output = resolve_single_horizon_dataset_output(
            args.dataset_output,
            args.horizon,
        )
        evaluation_output = resolve_single_horizon_evaluation_output(
            args.evaluation_output,
            args.horizon,
        )
        payload = run_prediction_lab(
            matrix=args.matrix,
            prices_dir=args.prices_dir,
            dataset_output=dataset_output,
            evaluation_output=evaluation_output,
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
