from __future__ import annotations

import json
from typing import Any

from pymercator.borrow_data import (
    diagnose_borrow_data,
    import_borrow_file,
    load_borrow_data,
    render_borrow_diagnose,
    render_borrow_show,
)
from pymercator.terminal_render import render_key_values, render_section


def run_borrow_command(args: Any) -> int:
    command = getattr(args, "borrow_command", "") or "show"
    json_output = bool(getattr(args, "json", False))

    if command == "show":
        status, records = load_borrow_data(getattr(args, "file", "") or None)
        if json_output:
            print(
                json.dumps(
                    {
                        "command": "borrow show",
                        "status": status,
                        "records": list(records.values()),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(render_borrow_show(status, records))
        return 0 if status.get("status") in {"OK", "PARTIAL", "STALE"} else 1

    if command == "import":
        payload = import_borrow_file(
            getattr(args, "file"),
            output=(getattr(args, "output", "") or None),
        )
        if json_output:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            lines = [
                render_key_values(
                    "BORROW IMPORT",
                    [
                        ("status", payload.get("status", "-")),
                        ("source", payload.get("source", "-")),
                        ("output", payload.get("output", "-")),
                        ("rows", payload.get("rows", 0)),
                    ],
                )
            ]
            if payload.get("errors"):
                lines.extend(["", render_section("ERRORS")])
                lines.extend(f"- {error}" for error in payload.get("errors", []))
            print("\n".join(lines))
        return 0 if payload.get("status") == "OK" else 1

    if command == "diagnose":
        payload = diagnose_borrow_data(
            path=(getattr(args, "file", "") or None),
            tickers_file=getattr(args, "tickers_file", "data/universes/ibov_live.csv"),
        )
        if json_output:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_borrow_diagnose(payload))
        return 0 if payload.get("status") in {"OK", "PARTIAL", "STALE"} else 1

    raise ValueError(f"unknown borrow command: {command}")
