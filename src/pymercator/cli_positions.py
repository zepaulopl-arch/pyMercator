from __future__ import annotations

import json
from typing import Any

from pymercator.position_actions import (
    DEFAULT_POSITIONS_PATH,
    import_positions_file,
    load_positions,
    position_actions_to_json,
    positions_to_dicts,
    render_positions,
)


def run_positions_command(args: Any) -> int:
    command = getattr(args, "pos_command", "") or "show"
    json_output = bool(getattr(args, "json", False) or getattr(args, "pos_json", False))
    if command == "show":
        source = getattr(args, "file", DEFAULT_POSITIONS_PATH)
        positions = load_positions(source)
        if json_output:
            print(
                json.dumps(
                    {
                        "command": "pos show",
                        "source": source,
                        "positions": positions_to_dicts(positions),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(render_positions(positions, source=source))
        return 0

    if command == "import":
        payload = import_positions_file(
            getattr(args, "file"),
            output=getattr(args, "output", DEFAULT_POSITIONS_PATH),
        )
        if json_output:
            print(position_actions_to_json(payload))
        else:
            print(
                "POSITIONS IMPORTED\n"
                "--------------------------------------------------------------------------------\n"
                f"source    {payload['source']}\n"
                f"output    {payload['output']}\n"
                f"positions {payload['positions']}"
            )
        return 0

    raise ValueError(f"unknown pos command: {command}")
