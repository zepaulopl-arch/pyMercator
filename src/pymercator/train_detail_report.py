from __future__ import annotations

from typing import Any


def render_train_detail_report(
    payload: dict[str, Any],
    *,
    include_engines: bool = False,
    include_prob_dist: bool = False,
    full: bool = False,
) -> str:
    # Kept as a module boundary for the operational CLI. The implementation is
    # delegated to the legacy renderer during this small-risk extraction pass.
    from pymercator.cli_train import render_train_detail_report as legacy_renderer

    return legacy_renderer(
        payload,
        include_engines=include_engines,
        include_prob_dist=include_prob_dist,
        full=full,
    )
