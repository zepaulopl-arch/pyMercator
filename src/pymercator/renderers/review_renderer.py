from __future__ import annotations

from typing import Any


def render_review(payload: dict[str, Any] | str | None) -> str:
    """Render review output without changing review logic."""
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    return str(payload)
