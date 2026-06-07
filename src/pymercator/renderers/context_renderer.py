from __future__ import annotations

from typing import Any


def render_context(payload: dict[str, Any] | str | None) -> str:
    """Render context output without changing context logic."""
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    return str(payload)
