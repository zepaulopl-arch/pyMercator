from __future__ import annotations

from pathlib import Path

from pymercator.data.universe_csv import load_universe_csv as _load_universe_csv
from pymercator.domain import AssetSnapshot


def load_universe_csv(path: str | Path) -> list[AssetSnapshot]:
    return _load_universe_csv(path)
