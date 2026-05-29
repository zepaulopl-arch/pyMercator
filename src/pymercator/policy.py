from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_POLICY_PATH = Path("config/policy.json")


def load_policy(path: str | Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    policy_path = Path(path)
    if not policy_path.exists():
        raise FileNotFoundError(f"Policy file not found: {policy_path}")

    with policy_path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def normalize_profile(profile: str) -> str:
    aliases = {
        "CONSERVATIVE": "CON",
        "CONSERVADOR": "CON",
        "BALANCED": "BAL",
        "BALANCEADO": "BAL",
        "AGGRESSIVE": "AGR",
        "AGRESSIVO": "AGR",
        "RELAXED": "RLX",
        "RELAXADO": "RLX",
    }

    normalized = profile.strip().upper()
    return aliases.get(normalized, normalized)


def get_profile_policy(policy: dict[str, Any], profile: str) -> dict[str, Any]:
    normalized = normalize_profile(profile)
    profiles = policy.get("profiles", {})

    if normalized not in profiles:
        allowed = ", ".join(sorted(profiles))
        raise ValueError(f"Unknown profile: {profile}. Allowed profiles: {allowed}")

    return profiles[normalized]