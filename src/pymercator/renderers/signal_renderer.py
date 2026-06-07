from __future__ import annotations

from typing import Any


def render_signal(payload: dict[str, Any] | str | None) -> str:
    """Render signal output.

    For Etapa 7 this is intentionally thin. Existing command output is preserved.
    """
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    return str(payload)
