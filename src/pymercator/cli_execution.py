from __future__ import annotations

import json
from typing import Any

from pymercator.execution_policy import (
    validate_execution_policy,
    write_execution_policy_template,
)


def run_execution_command(args: Any) -> int:
    if args.execution_command == "template":
        write_execution_policy_template(args.output)
        print(f"Execution policy template written to: {args.output}")
        return 0

    if args.execution_command == "check":
        payload = validate_execution_policy(args.file)

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR EXECUTION POLICY CHECK")
            print("-" * 100)
            print(f"{'FILE':<24} {payload['path']}")
            print(f"{'VALID':<24} {payload['valid']}")

            policy = payload.get("policy", {})
            if policy:
                print(f"{'EXECUTION MODE':<24} {policy['execution_mode']}")
                print(f"{'ORDER ROUTING':<24} {policy['allow_order_routing']}")
                print(
                    f"{'HUMAN CONFIRMATION':<24} "
                    f"{policy['require_human_confirmation']}"
                )

            if payload["errors"]:
                print("")
                print("ERRORS")
                print("-" * 100)
                for error in payload["errors"]:
                    print(f"- {error}")

        return 0 if payload["valid"] else 1

    raise ValueError(f"Unknown execution command: {args.execution_command}")
