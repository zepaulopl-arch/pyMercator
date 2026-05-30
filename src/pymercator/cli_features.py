from __future__ import annotations

import json
from typing import Any

from pymercator.features_catalog import (
    render_features_catalog,
    validate_features_catalog,
)
from pymercator.features_matrix import (
    render_feature_matrix_summary,
    write_feature_matrix,
)


def run_features_command(args: Any) -> int:
    if args.features_command in {"check", "catalog"}:
        payload = validate_features_catalog(args.file)

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_features_catalog(payload))

        return 0 if payload["valid"] else 1

    if args.features_command == "matrix":
        payload = write_feature_matrix(
            universe=args.universe,
            prices_dir=args.prices_dir,
            context=args.context,
            features=args.features,
            output=args.output,
        )

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_feature_matrix_summary(payload))

        return 0

    raise ValueError(f"Unknown features command: {args.features_command}")
