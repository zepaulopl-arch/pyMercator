from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

from pymercator.data.ticker_list import normalize_ticker, validate_ticker_list_csv

TICKER_KEYS = {
    "ticker",
    "tickers",
    "symbol",
    "symbols",
    "code",
    "codes",
    "asset",
    "assets",
    "ativo",
    "ativos",
}

SECTOR_KEYS = {
    "sector",
    "setor",
    "industry",
    "segment",
    "segmento",
    "group",
    "grupo",
}

DEFAULT_SECTOR = "UNKNOWN"


def _load_yaml(path: Path) -> Any:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML is not installed. Run: python -m pip install -e ."
        ) from exc

    if not path.exists():
        return None

    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _looks_like_ticker(value: str) -> bool:
    text = value.strip().upper()

    if not text:
        return False

    text = text.replace(".SA", "")
    return bool(re.fullmatch(r"[A-Z]{4}[0-9]{1,2}[A-Z]?", text))


def _base_ticker(value: str) -> str:
    ticker = normalize_ticker(value)

    if ticker.endswith(".SA"):
        return ticker[:-3]

    return ticker


def _extract_sector(record: dict[str, Any]) -> str:
    for key, value in record.items():
        if str(key).lower() in SECTOR_KEYS and value:
            return str(value).strip()

    nested_keys = ("info", "metadata", "meta", "profile", "asset")
    for nested_key in nested_keys:
        nested = record.get(nested_key)
        if isinstance(nested, dict):
            sector = _extract_sector(nested)
            if sector != DEFAULT_SECTOR:
                return sector

    return DEFAULT_SECTOR


def _extract_ticker_from_record(record: dict[str, Any]) -> str:
    for key, value in record.items():
        key_text = str(key).lower()

        if key_text in TICKER_KEYS and isinstance(value, str):
            if _looks_like_ticker(value):
                return normalize_ticker(value)

    for key in ("name", "id"):
        value = record.get(key)
        if isinstance(value, str) and _looks_like_ticker(value):
            return normalize_ticker(value)

    return ""


def _walk_assets(node: Any, found: dict[str, str]) -> None:
    if isinstance(node, dict):
        ticker = _extract_ticker_from_record(node)

        if ticker:
            base = _base_ticker(ticker)
            found[base] = _extract_sector(node)

        for key, value in node.items():
            if isinstance(key, str) and _looks_like_ticker(key):
                base = _base_ticker(key)

                if isinstance(value, dict):
                    found[base] = _extract_sector(value)
                elif base not in found:
                    found[base] = DEFAULT_SECTOR

            _walk_assets(value, found)

    elif isinstance(node, list):
        for item in node:
            if isinstance(item, str) and _looks_like_ticker(item):
                base = _base_ticker(item)
                found.setdefault(base, DEFAULT_SECTOR)
            else:
                _walk_assets(item, found)


def _walk_universe_tickers(node: Any, found: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            key_text = str(key).lower()

            if key_text in TICKER_KEYS:
                if isinstance(value, str) and _looks_like_ticker(value):
                    found.add(_base_ticker(value))
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str) and _looks_like_ticker(item):
                            found.add(_base_ticker(item))
                        elif isinstance(item, dict):
                            ticker = _extract_ticker_from_record(item)
                            if ticker:
                                found.add(_base_ticker(ticker))

            if isinstance(key, str) and _looks_like_ticker(key):
                found.add(_base_ticker(key))

            _walk_universe_tickers(value, found)

    elif isinstance(node, list):
        for item in node:
            if isinstance(item, str) and _looks_like_ticker(item):
                found.add(_base_ticker(item))
            else:
                _walk_universe_tickers(item, found)


def load_legacy_universe(
    *,
    legacy_path: str | Path,
    assets_file: str = "config/assets/ibov_assets.yaml",
    universe_file: str = "config/universes/ibov.yaml",
) -> dict[str, Any]:
    root = Path(legacy_path)
    assets_path = root / assets_file
    universe_path = root / universe_file

    assets_payload = _load_yaml(assets_path)
    universe_payload = _load_yaml(universe_path)

    asset_sector_map: dict[str, str] = {}
    universe_tickers: set[str] = set()

    _walk_assets(assets_payload, asset_sector_map)
    _walk_universe_tickers(universe_payload, universe_tickers)

    if universe_tickers:
        selected_bases = sorted(universe_tickers)
    else:
        selected_bases = sorted(asset_sector_map)

    rows = [
        {
            "ticker": f"{base}.SA",
            "sector": asset_sector_map.get(base, DEFAULT_SECTOR),
        }
        for base in selected_bases
    ]

    return {
        "legacy_path": str(root),
        "assets_path": str(assets_path),
        "universe_path": str(universe_path),
        "assets_found": len(asset_sector_map),
        "universe_tickers_found": len(universe_tickers),
        "rows": rows,
        "row_count": len(rows),
        "unknown_sector_count": sum(
            1 for row in rows if row["sector"] == DEFAULT_SECTOR
        ),
    }


def write_legacy_universe_ticker_list(
    *,
    legacy_path: str | Path,
    output: str | Path,
    assets_file: str = "config/assets/ibov_assets.yaml",
    universe_file: str = "config/universes/ibov.yaml",
) -> dict[str, Any]:
    payload = load_legacy_universe(
        legacy_path=legacy_path,
        assets_file=assets_file,
        universe_file=universe_file,
    )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=("ticker", "sector"))
        writer.writeheader()
        writer.writerows(payload["rows"])

    validation = validate_ticker_list_csv(output_path)

    return {
        "legacy_path": payload["legacy_path"],
        "assets_path": payload["assets_path"],
        "universe_path": payload["universe_path"],
        "output": str(output_path),
        "assets_found": payload["assets_found"],
        "universe_tickers_found": payload["universe_tickers_found"],
        "rows": payload["row_count"],
        "unknown_sector_count": payload["unknown_sector_count"],
        "valid": validation["valid"],
        "validation": validation,
    }
