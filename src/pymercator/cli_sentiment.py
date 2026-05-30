from __future__ import annotations

import json
from typing import Any

from pymercator.sentiment_store import check_sentiment_dir, render_sentiment_check


def run_sentiment_command(args: Any) -> int:
    if args.sentiment_command == "check":
        payload = check_sentiment_dir(args.sentiment_dir)

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_sentiment_check(payload))

        return 0 if payload["exists"] and payload["invalid_files"] == 0 else 1

    raise ValueError(f"Unknown sentiment command: {args.sentiment_command}")
