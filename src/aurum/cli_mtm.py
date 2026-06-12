from __future__ import annotations

import json
from typing import Any

from aurum.observation_review import (
    render_observation_review,
    run_observation_review,
)


def run_mtm_command(args: Any) -> int:
    if not getattr(args, "run_dir", ""):
        from aurum.core import run_review

        payload = run_review(
            profile=args.profile,
            list_name=getattr(args, "list", "IBOV"),
            signal_date=getattr(args, "signal_date", "") or None,
            review_date=getattr(args, "review_date", "") or None,
            signals_dir=getattr(args, "signals_dir", "storage/signals"),
            prices_dir=args.prices_dir,
            review_limit=getattr(args, "review_limit", 10),
        )

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(payload["text"], end="")

        return 0

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
