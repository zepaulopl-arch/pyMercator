from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_EXECUTION_POLICY = {
    "execution_mode": "ANALYSIS_ONLY",
    "allow_order_routing": False,
    "require_human_confirmation": True,
}

VALID_EXECUTION_MODES = {"ANALYSIS_ONLY"}


def load_execution_policy(path: str | Path = "config/execution_policy.json") -> dict[str, Any]:
    policy_path = Path(path)

    if not policy_path.exists():
        return dict(DEFAULT_EXECUTION_POLICY)

    payload = json.loads(policy_path.read_text(encoding="utf-8-sig"))

    policy = dict(DEFAULT_EXECUTION_POLICY)
    policy.update(payload)

    policy["execution_mode"] = str(policy["execution_mode"]).upper()
    policy["allow_order_routing"] = bool(policy["allow_order_routing"])
    policy["require_human_confirmation"] = bool(policy["require_human_confirmation"])

    return policy


def validate_execution_policy(
    path: str | Path = "config/execution_policy.json",
) -> dict[str, Any]:
    errors: list[str] = []

    try:
        policy = load_execution_policy(path)
    except Exception as exc:
        return {
            "path": str(path),
            "valid": False,
            "errors": [str(exc)],
            "policy": {},
        }

    if policy["execution_mode"] not in VALID_EXECUTION_MODES:
        errors.append(
            "execution_mode must be ANALYSIS_ONLY"
        )

    if policy["allow_order_routing"] is not False:
        errors.append(
            "allow_order_routing must be false"
        )

    if policy["require_human_confirmation"] is not True:
        errors.append(
            "require_human_confirmation must be true"
        )

    return {
        "path": str(path),
        "valid": not errors,
        "errors": errors,
        "policy": policy,
    }


def write_execution_policy_template(
    path: str | Path = "config/execution_policy.json",
) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)

    output.write_text(
        json.dumps(DEFAULT_EXECUTION_POLICY, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
