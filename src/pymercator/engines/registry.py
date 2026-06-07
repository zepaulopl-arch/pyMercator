from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class EngineSpec:
    name: str
    backend: str
    enabled: bool = True
    supports_importance: bool = True
    deterministic: bool = False
    role: str = "base"
    description: str = ""


ENGINE_REGISTRY: list[EngineSpec] = [
    EngineSpec(
        name="extratrees",
        backend="sklearn",
        enabled=True,
        supports_importance=True,
        deterministic=False,
        role="base",
        description="Extra Trees base learner.",
    ),
    EngineSpec(
        name="randomforest",
        backend="sklearn",
        enabled=True,
        supports_importance=True,
        deterministic=False,
        role="base",
        description="Random Forest base learner.",
    ),
    EngineSpec(
        name="gradientboosting",
        backend="sklearn",
        enabled=True,
        supports_importance=True,
        deterministic=True,
        role="base",
        description="Gradient Boosting base learner.",
    ),
    EngineSpec(
        name="ridge_meta",
        backend="sklearn",
        enabled=True,
        supports_importance=False,
        deterministic=True,
        role="meta",
        description="Ridge meta combiner / ensemble observer inside each horizon.",
    ),
]


def list_engines() -> list[dict[str, Any]]:
    return [asdict(spec) for spec in ENGINE_REGISTRY]


def engine_names() -> list[str]:
    return [spec.name for spec in ENGINE_REGISTRY]


def get_engine(name: str) -> EngineSpec | None:
    normalized = str(name).strip().lower()

    aliases = {
        "ridge": "ridge_meta",
        "ridge_ensemble": "ridge_meta",
        "meta_ridge": "ridge_meta",
    }

    normalized = aliases.get(normalized, normalized)

    for spec in ENGINE_REGISTRY:
        if spec.name == normalized:
            return spec

    return None


def print_engine_list() -> None:
    print("AURUM ENGINE LIST")
    print("-" * 80)
    print(f"{'engine':<20} {'backend':<10} {'role':<8} {'enabled':<8} {'importance':<11} {'deterministic':<13}")

    for spec in ENGINE_REGISTRY:
        print(
            f"{spec.name:<20} "
            f"{spec.backend:<10} "
            f"{spec.role:<8} "
            f"{'yes' if spec.enabled else 'no':<8} "
            f"{'yes' if spec.supports_importance else 'no':<11} "
            f"{'yes' if spec.deterministic else 'no':<13}"
        )
