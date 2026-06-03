from __future__ import annotations

import json
from typing import Any

from pymercator.observation import render_observation_report, run_observation


def run_observe_command(args: Any) -> int:
    payload = run_observation(
        universe=args.universe,
        list_name=args.list,
        config_path=args.config,
        limit=args.limit,
        cluster=bool(getattr(args, "cluster", False)),
    )

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_observation_report(payload, limit=args.limit))
    return 0
