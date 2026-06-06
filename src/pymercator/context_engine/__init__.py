"""Aurum Context Engine.

Official-source-first context builder with local fallbacks and explicit
source_status. It does not invent missing data.
"""

from pymercator.context_engine.builder import build_market_context
from pymercator.context_engine.renderer import (
    render_context_audit,
    render_context_explain,
    render_context_show,
)

__all__ = [
    "build_market_context",
    "render_context_audit",
    "render_context_explain",
    "render_context_show",
]
