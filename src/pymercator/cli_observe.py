from __future__ import annotations

import json
from typing import Any

from pymercator.observation import (
    calibrate_observation_thresholds,
    render_observation_report,
    run_observation,
)
from pymercator.terminal_render import render_key_values, render_section


def run_observe_command(args: Any) -> int:
    if getattr(args, "observe_command", "run") == "calibrate":
        payload = calibrate_observation_thresholds(
            universe=args.universe,
            list_name=args.list,
            config_path=args.config,
            output=getattr(args, "output", ""),
        )
        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            lines = [
                render_key_values(
                    "OBSERVATION CALIBRATION",
                    [
                        ("LIST", payload["list"]),
                        ("UNIVERSE", payload["universe"]),
                        ("ASSETS", payload["asset_count"]),
                        ("OUTPUT", payload.get("output", "-")),
                    ],
                ),
                "",
                render_section("THRESHOLDS"),
            ]
            lines.extend(
                f"{key:<24} {float(value):>7.2f}"
                for key, value in payload["thresholds"].items()
            )
            print("\n".join(lines))
        return 0

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
