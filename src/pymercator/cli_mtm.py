from __future__ import annotations

import json
from typing import Any

from pymercator.observation_review import (
    render_observation_review,
    run_observation_review,
)


def run_mtm_command(args: Any) -> int:
    payload = run_observation_review(
        run_dir=args.run_dir,
        capital=args.capital,
        mode=args.mode,
        prices_dir=args.prices_dir,
        profile=args.profile,
        relevance_pct=args.relevance_pct,
    )

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_observation_review(payload))

    return 0
