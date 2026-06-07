from __future__ import annotations

from typing import Any


def render_train(payload: dict[str, Any] | str | None) -> str:
    """Render train output without changing train logic."""
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    return str(payload)
