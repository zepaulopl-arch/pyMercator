from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from pymercator.ui import (
    colorize,
    format_kv,
    format_kv_section,
    format_table,
    format_title,
    muted_line,
    strip_ansi,
    truncate,
)

TableRow = Mapping[str, Any] | Sequence[Any]


def render_section(title: str, *, width: int = 80, color: bool | None = None) -> str:
    return format_title(title, width=width, color=color)


def render_key_values(
    title: str,
    rows: list[tuple[str, Any] | tuple[str, Any, Any]],
    *,
    label_width: int = 18,
    width: int = 80,
    color: bool | None = None,
) -> str:
    return format_kv_section(
        title,
        rows,
        label_width=label_width,
        width=width,
        color=color,
    )


def render_table(
    title: str,
    headers: Sequence[str],
    rows: Iterable[TableRow],
    *,
    widths: Sequence[int] | None = None,
    color: bool | None = None,
    width: int = 80,
) -> str:
    headers = list(headers)
    widths = list(widths or [max(8, len(header)) for header in headers])
    columns = [(header, header, widths[index]) for index, header in enumerate(headers)]
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, Mapping):
            normalized.append({header: row.get(header, "") for header in headers})
        else:
            values = list(row)
            normalized.append(
                {
                    header: values[index] if index < len(values) else ""
                    for index, header in enumerate(headers)
                }
            )
    return format_table(title, columns, normalized, color=color, width=width)


def render_files(
    rows: list[tuple[str, Any] | tuple[str, Any, Any]],
    *,
    label_width: int = 18,
    width: int = 80,
) -> str:
    return render_key_values("FILES", rows, label_width=label_width, width=width)


def render_legend(rows: Iterable[str], *, title: str = "LEGEND", width: int = 80) -> str:
    items = [str(row) for row in rows if str(row).strip()]
    if not items:
        return ""
    return "\n".join([render_section(title, width=width), *items])


def render_empty_state(
    title: str,
    *,
    reason: str,
    status: str = "EMPTY",
    width: int = 80,
) -> str:
    return "\n".join(
        [
            render_section(title, width=width),
            format_kv("status", status),
            format_kv("reason", reason),
        ]
    )


def colorize_status(value: Any, status: Any | None = None, *, color: bool | None = None) -> str:
    return colorize(value, status if status is not None else value, enabled=color)


__all__ = [
    "colorize_status",
    "format_kv",
    "muted_line",
    "render_empty_state",
    "render_files",
    "render_key_values",
    "render_legend",
    "render_section",
    "render_table",
    "strip_ansi",
    "truncate",
]
