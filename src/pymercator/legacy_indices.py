from __future__ import annotations

from pathlib import Path
from typing import Any

from pymercator.indices_catalog import write_indices_catalog

SYMBOL_KEYS = {
    "symbol",
    "ticker",
    "yahoo",
    "yahoo_symbol",
    "yahoo_ticker",
    "yf",
}

NAME_KEYS = {
    "name",
    "label",
    "title",
}

CATEGORY_KEYS = {
    "category",
    "type",
    "group",
    "class",
}

DESCRIPTION_KEYS = {
    "description",
    "desc",
    "notes",
}


OPTIONAL_SYMBOLS = {
    "IFNC.SA",
    "^IEE",
}


def _is_required_symbol(symbol: str) -> bool:
    return symbol.strip().upper() not in OPTIONAL_SYMBOLS


def _load_yaml(path: Path) -> Any:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML is not installed. Run: python -m pip install -e ."
        ) from exc

    if not path.exists():
        raise FileNotFoundError(f"Legacy indices catalog not found: {path}")

    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _first_text(record: dict[str, Any], keys: set[str], default: str = "") -> str:
    for key, value in record.items():
        if str(key).lower() in keys and value is not None:
            return str(value).strip()

    return default


def _looks_like_symbol(value: str) -> bool:
    text = value.strip().upper()

    if not text:
        return False

    if len(text) > 32:
        return False

    if " " in text or "_" in text:
        return False

    blocked = {
        "YFINANCE",
        "DERIVED",
        "FUTURE",
        "FUTURE_B3_OR_YFINANCE",
        "PENDING_PROVIDER_VALIDATION",
        "USE_IEEX_UNTIL_DIRECT_PROVIDER",
        "BENCHMARK_MARKET",
        "COMMODITY_OIL",
        "SECTOR_FINANCIALS",
        "SECTOR_UTILITIES",
        "SECTOR_MATERIALS",
        "SECTOR_INDUSTRIALS",
        "SECTOR_REAL_ESTATE",
        "SECTOR_CONSUMPTION",
        "STYLE_DIVIDENDS",
        "STYLE_SMALL_CAPS",
        "LARGE_CAPS",
        "FX",
    }

    if text in blocked:
        return False

    if text.startswith("^"):
        return True

    if text.endswith(".SA"):
        return True

    if text.endswith("=X"):
        return True

    if text.endswith("=F"):
        return True

    if "." in text and any(char.isalpha() for char in text):
        return True

    return False


def _record_from_dict(
    *,
    key_hint: str,
    record: dict[str, Any],
    parent_category: str = "market",
) -> dict[str, str] | None:
    symbol = _first_text(record, SYMBOL_KEYS)

    if not symbol or not _looks_like_symbol(symbol):
        return None

    name = _first_text(record, NAME_KEYS, default=key_hint)
    category = _first_text(record, CATEGORY_KEYS, default=parent_category)
    description = _first_text(record, DESCRIPTION_KEYS)

    provider = str(record.get("provider", "yfinance")).strip() or "yfinance"

    return {
        "name": name or symbol,
        "symbol": symbol,
        "provider": provider,
        "category": category or "market",
        "description": description,
        "required": _is_required_symbol(symbol),
        "enabled": True,
    }


def _has_symbol_field(record: dict[str, Any]) -> bool:
    return any(str(key).lower() in SYMBOL_KEYS for key in record)


def _walk_catalog(
    node: Any,
    *,
    key_hint: str = "",
    parent_category: str = "market",
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    if isinstance(node, dict):
        current_category = _first_text(node, CATEGORY_KEYS, default=parent_category)

        if _has_symbol_field(node):
            maybe_record = _record_from_dict(
                key_hint=key_hint,
                record=node,
                parent_category=current_category,
            )
            return [maybe_record] if maybe_record else []

        for key, value in node.items():
            key_text = str(key)

            if isinstance(value, dict):
                rows.extend(
                    _walk_catalog(
                        value,
                        key_hint=key_text,
                        parent_category=current_category,
                    )
                )
            elif isinstance(value, list):
                rows.extend(
                    _walk_catalog(
                        value,
                        key_hint=key_text,
                        parent_category=current_category,
                    )
                )
            elif (
                str(key).lower() in SYMBOL_KEYS
                and isinstance(value, str)
                and _looks_like_symbol(value)
            ):
                rows.append(
                    {
                        "name": key_text,
                        "symbol": value.strip(),
                        "provider": "yfinance",
                        "category": current_category,
                        "description": "",
                        "required": _is_required_symbol(value),
                        "enabled": True,
                    }
                )

    elif isinstance(node, list):
        for item in node:
            rows.extend(
                _walk_catalog(
                    item,
                    key_hint=key_hint,
                    parent_category=parent_category,
                )
            )

    elif (
        key_hint.lower() in SYMBOL_KEYS
        and isinstance(node, str)
        and _looks_like_symbol(node)
    ):
        rows.append(
            {
                "name": key_hint or node,
                "symbol": node.strip(),
                "provider": "yfinance",
                "category": parent_category,
                "description": "",
                "required": _is_required_symbol(node),
                "enabled": True,
            }
        )

    return rows


def _dedupe(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_symbol: dict[str, dict[str, str]] = {}

    for row in rows:
        symbol = row["symbol"]
        if symbol not in by_symbol:
            by_symbol[symbol] = row

    return list(by_symbol.values())


def migrate_legacy_indices_catalog(
    *,
    legacy_path: str | Path,
    output: str | Path,
    catalog_file: str = "config/indices/catalog.yaml",
) -> dict[str, Any]:
    root = Path(legacy_path)
    catalog_path = root / catalog_file

    payload = _load_yaml(catalog_path)
    rows = _dedupe(_walk_catalog(payload))

    result = write_indices_catalog(
        output=output,
        indices=rows,
    )

    return {
        "legacy_path": str(root),
        "catalog_path": str(catalog_path),
        "output": result["output"],
        "count": result["count"],
        "valid": result["valid"],
        "errors": result["errors"],
        "indices": result["indices"],
    }
