from __future__ import annotations

import math
from typing import Any


def line(width: int = 100) -> str:
    return "-" * max(1, int(width))


def kv(label: str, value: object, label_width: int = 22) -> str:
    return f"{label:<{label_width}} {value}"


def short_path(path: str | None, max_len: int = 70) -> str:
    if not path:
        return "-"

    text = str(path)
    if len(text) <= max_len:
        return text

    half = max_len // 2 - 2
    return f"{text[:half]}...{text[-half:]}"


def render_table(rows: list[dict[str, Any]], columns: list[str], widths: dict[str, int] | None = None) -> str:
    if not rows:
        return ""

    widths = widths or {}
    col_widths = {col: widths.get(col, max(10, len(col))) for col in columns}

    header = "  ".join(f"{col:<{col_widths[col]}}" for col in columns)
    lines = [header, line(len(header))]

    for row in rows:
        line_text = "  ".join(
            f"{str(row.get(col, '')):<{col_widths[col]}}" for col in columns
        )
        lines.append(line_text)

    return "\n".join(lines)


def status_label(status: str) -> str:
    return status


def section(title: str, width: int = 100) -> str:
    title_text = f" {title} "
    pad = max(0, width - len(title_text))
    left = pad // 2
    right = pad - left
    return f"{"-"*left}{title_text}{"-"*right}"


def render_warning_list(warnings: list[str] | None, prefix: str = "- ") -> str:
    if not warnings:
        return ""

    lines = ["WARNINGS", line()]
    for w in warnings:
        lines.append(f"{prefix}{w}")

    return "\n".join(lines)
