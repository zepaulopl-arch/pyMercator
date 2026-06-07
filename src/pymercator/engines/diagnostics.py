from __future__ import annotations

from .registry import ENGINE_REGISTRY
from .scoreboard import build_scoreboard


def explain_engines() -> None:
    scoreboard = build_scoreboard()
    rows = scoreboard.get("rows", [])

    print("AURUM ENGINE EXPLAIN")
    print("-" * 80)

    print("This registry measures the engines already used by the current Aurum stack.")
    print("No XGBoost, CatBoost, backend change, default engine change, or observer weight change is made here.")
    print()

    print("STACK")
    print("-" * 80)
    for spec in ENGINE_REGISTRY:
        print(f"{spec.name:<20} role={spec.role:<5} backend={spec.backend:<8} enabled={'yes' if spec.enabled else 'no'}")

    print()
    print("READ")
    print("-" * 80)

    best = scoreboard.get("best_engine")
    horizon = scoreboard.get("most_reliable_horizon")
    hurting = scoreboard.get("hurting_engines") or []

    least_bad = scoreboard.get("least_bad_engine")

    print(f"best_engine             {best or '-'}")
    print(f"least_bad_engine        {least_bad or '-'}")
    print(f"most_reliable_horizon   {horizon or '-'}")
    print(f"hurting_engines         {', '.join(hurting) if hurting else 'none'}")

    print()
    print("ENGINE NOTES")
    print("-" * 80)

    for row in rows:
        engine = row.get("engine", "-")
        status = row.get("status", "-")
        edge = row.get("edge")

        if edge is None:
            note = "not found in latest evaluation artifacts"
        elif status == "BEST":
            note = "best current measured edge"
        elif status == "LEAST_BAD":
            note = "best among weak engines, but still negative edge"
        elif status == "BAD":
            note = "negative average edge; candidate to investigate"
        elif status == "WEAK":
            note = "near-flat edge; not clearly helping"
        else:
            note = "positive measured edge"

        print(f"{engine:<20} {status:<8} {note}")
