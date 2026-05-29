from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

IGNORED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "site-packages",
}

TEXT_EXTENSIONS = {
    ".py",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".csv",
    ".txt",
    ".md",
    ".ini",
    ".cfg",
    ".ps1",
    ".bat",
}

DATA_EXTENSIONS = {
    ".csv",
    ".json",
    ".parquet",
    ".pkl",
    ".pickle",
    ".xlsx",
    ".db",
    ".sqlite",
}

KEYWORDS = {
    "assets": (
        "ibov",
        "ticker",
        "tickers",
        "asset",
        "assets",
        "universe",
        "symbols",
        "acoes",
        "ativos",
    ),
    "features": (
        "feature",
        "features",
        "indicator",
        "indicators",
        "technical",
        "momentum",
        "trend",
        "atr",
        "rsi",
        "macd",
        "bollinger",
    ),
    "models": (
        "model",
        "models",
        "predict",
        "prediction",
        "forecast",
        "ml",
        "xgboost",
        "lightgbm",
        "lstm",
        "ensemble",
        "train",
    ),
    "fundamentals": (
        "fundamental",
        "fundamentals",
        "fundamentos",
        "dre",
        "balance",
        "valuation",
        "pl",
        "roe",
        "roic",
        "ebitda",
    ),
    "news": (
        "news",
        "noticia",
        "noticias",
        "headline",
        "sentiment",
        "rss",
    ),
    "indices": (
        "index",
        "indices",
        "indice",
        "ibov",
        "bova",
        "sp500",
        "dxy",
        "vix",
        "selic",
        "cdi",
    ),
    "backtests": (
        "backtest",
        "backtesting",
        "simulate",
        "simulation",
        "simulacao",
        "strategy",
        "strategies",
    ),
    "reports": (
        "report",
        "reports",
        "summary",
        "dashboard",
        "terminal",
        "plot",
        "chart",
    ),
}


def _should_ignore_dir(path: Path) -> bool:
    return path.name in IGNORED_DIRS


def _relative(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _category_for_path(path: Path) -> list[str]:
    text = str(path).lower()
    categories: list[str] = []

    for category, keywords in KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            categories.append(category)

    return categories or ["uncategorized"]


def _safe_read_head(path: Path, max_chars: int = 20_000) -> str:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return ""

    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except OSError:
        return ""


def _content_hints(path: Path) -> list[str]:
    text = _safe_read_head(path).lower()
    hints: list[str] = []

    if not text:
        return hints

    if "class " in text:
        hints.append("classes")

    if "def " in text:
        hints.append("functions")

    if "import sklearn" in text or "from sklearn" in text:
        hints.append("sklearn")

    if "xgboost" in text:
        hints.append("xgboost")

    if "lightgbm" in text:
        hints.append("lightgbm")

    if "tensorflow" in text or "keras" in text or "torch" in text:
        hints.append("deep_learning")

    if "yfinance" in text:
        hints.append("yfinance")

    if "requests" in text or "beautifulsoup" in text or "bs4" in text:
        hints.append("web_fetch")

    if "backtest" in text or "simulate" in text:
        hints.append("simulation")

    if "news" in text or "headline" in text or "sentiment" in text:
        hints.append("news")

    return sorted(set(hints))


def scan_legacy_project(path: str | Path) -> dict[str, Any]:
    root = Path(path).expanduser().resolve()

    if not root.exists():
        raise FileNotFoundError(f"Legacy path not found: {root}")

    files: list[dict[str, Any]] = []
    ignored_dirs: list[str] = []

    for item in root.rglob("*"):
        if item.is_dir() and _should_ignore_dir(item):
            ignored_dirs.append(_relative(item, root))
            continue

        if not item.is_file():
            continue

        if any(part in IGNORED_DIRS for part in item.parts):
            continue

        try:
            size_bytes = item.stat().st_size
        except OSError:
            size_bytes = 0

        suffix = item.suffix.lower()
        rel_path = _relative(item, root)

        files.append(
            {
                "path": rel_path,
                "name": item.name,
                "extension": suffix or "<none>",
                "size_bytes": size_bytes,
                "categories": _category_for_path(item),
                "content_hints": _content_hints(item),
                "is_python": suffix == ".py",
                "is_data": suffix in DATA_EXTENSIONS,
                "is_large": size_bytes >= 1_000_000,
            }
        )

    extension_counts = Counter(file["extension"] for file in files)
    category_counts: Counter[str] = Counter()

    for file in files:
        for category in file["categories"]:
            category_counts[category] += 1

    large_files = sorted(
        [file for file in files if file["is_large"]],
        key=lambda item: item["size_bytes"],
        reverse=True,
    )[:30]

    candidate_files = {
        category: [
            file
            for file in files
            if category in file["categories"]
        ][:50]
        for category in KEYWORDS
    }

    return {
        "root": str(root),
        "file_count": len(files),
        "python_files": sum(1 for file in files if file["is_python"]),
        "data_files": sum(1 for file in files if file["is_data"]),
        "large_files_count": sum(1 for file in files if file["is_large"]),
        "ignored_dirs": sorted(set(ignored_dirs)),
        "extension_counts": dict(sorted(extension_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "large_files": large_files,
        "candidate_files": candidate_files,
        "files": files,
    }


def render_legacy_inventory(payload: dict[str, Any]) -> str:
    line = "-" * 118
    lines: list[str] = []

    lines.append("PYMERCATOR LEGACY INVENTORY")
    lines.append(line)
    lines.append(f"{'ROOT':<20} {payload['root']}")
    lines.append(f"{'FILES':<20} {payload['file_count']}")
    lines.append(f"{'PYTHON FILES':<20} {payload['python_files']}")
    lines.append(f"{'DATA FILES':<20} {payload['data_files']}")
    lines.append(f"{'LARGE FILES':<20} {payload['large_files_count']}")
    lines.append("")

    lines.append("CATEGORY COUNTS")
    lines.append(line)

    for category, count in payload["category_counts"].items():
        lines.append(f"{category:<20} {count}")

    lines.append("")
    lines.append("EXTENSION COUNTS")
    lines.append(line)

    for extension, count in payload["extension_counts"].items():
        lines.append(f"{extension:<20} {count}")

    lines.append("")
    lines.append("CANDIDATES")
    lines.append(line)

    for category, files in payload["candidate_files"].items():
        lines.append("")
        lines.append(f"[{category.upper()}]")

        if not files:
            lines.append("-")
            continue

        for file in files[:15]:
            hints = ",".join(file["content_hints"]) or "-"
            lines.append(
                f"{file['path']:<72} "
                f"{file['extension']:<8} "
                f"{file['size_bytes']:>10} "
                f"hints={hints}"
            )

    lines.append("")
    lines.append("LARGE FILES")
    lines.append(line)

    if not payload["large_files"]:
        lines.append("-")
    else:
        for file in payload["large_files"]:
            lines.append(
                f"{file['path']:<72} "
                f"{file['extension']:<8} "
                f"{file['size_bytes']:>10}"
            )

    return "\n".join(lines)


def write_legacy_inventory(
    *,
    legacy_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    payload = scan_legacy_project(legacy_path)

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    text = render_legacy_inventory(payload)

    txt_path = output / "legacy_inventory.txt"
    json_path = output / "legacy_inventory.json"

    txt_path.write_text(text, encoding="utf-8")
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "legacy_path": payload["root"],
        "output_dir": str(output),
        "txt_path": str(txt_path),
        "json_path": str(json_path),
        "file_count": payload["file_count"],
        "python_files": payload["python_files"],
        "data_files": payload["data_files"],
        "large_files_count": payload["large_files_count"],
        "category_counts": payload["category_counts"],
    }
