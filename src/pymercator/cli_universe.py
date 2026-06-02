from __future__ import annotations

import json
from typing import Any

from pymercator.data.universe_builder import build_universe_csv_from_prices
from pymercator.data.universe_csv import (
    summarize_universe_csv,
    validate_universe_csv,
    write_universe_template,
)
from pymercator.data.universe_diagnostics import diagnose_universe_csv
from pymercator.ui import color_metric, colorize, format_kv_section, muted_line, short_sector


def _render_universe_check(payload: dict[str, Any]) -> str:
    line = "-" * 100
    lines = [
        "PYMERCATOR UNIVERSE CHECK",
        line,
        f"{'FILE':<20} {payload['path']}",
        f"{'VALID':<20} {payload['valid']}",
        f"{'ROWS':<20} {payload['rows']}",
        f"{'MISSING COLUMNS':<20} {', '.join(payload['missing_columns']) or '-'}",
        f"{'EXTRA COLUMNS':<20} {', '.join(payload['extra_columns']) or '-'}",
        f"{'DUPLICATES':<20} {', '.join(payload['duplicate_tickers']) or '-'}",
        f"{'ROW ERRORS':<20} {len(payload['row_errors'])}",
    ]

    if payload['row_errors']:
        lines.append("")
        lines.append("ERRORS")
        lines.append(line)
        for error in payload['row_errors'][:20]:
            lines.append(
                f"line={error['line']} field={error['field']} error={error['error']}"
            )

    return "\n".join(lines)


def _render_universe_summary(payload: dict[str, Any]) -> str:
    line = muted_line()
    lines = [
        format_kv_section(
            "PYMERCATOR UNIVERSE SUMMARY",
            [
                ("file", payload["path"]),
                ("assets", payload["assets"]),
                ("avg_volume_brl", f"{payload['avg_volume_brl']:.2f}"),
                ("avg_trend", f"{payload['avg_trend_score']:.2f}"),
                ("avg_momentum", f"{payload['avg_momentum_score']:.2f}"),
                ("avg_volatility", f"{payload['avg_volatility_pct']:.2f}"),
            ],
            label_width=18,
        ),
        "",
        "SECTORS",
        line,
    ]

    for sector, count in payload['sectors'].items():
        lines.append(f"{_fmt_sector(sector, 20):<20} {count}")

    lines.append("")
    lines.append("TOP VOLUME")
    lines.append(line)

    for item in payload['top_volume']:
        lines.append(
            f"{item['ticker']:<8} "
            f"{_fmt_sector(item['sector'], 14):<14} "
            f"{item['avg_volume_brl']:>14.2f}"
        )

    return "\n".join(lines)


def _fmt_sector(value: object, width: int = 24) -> str:
    return short_sector(value, width)


def _render_sector_warning_summary(payload: dict[str, Any]) -> list[str]:
    line = muted_line()
    rows = payload.get("sector_warning_summary", [])
    lines = [
        "SECTOR WARNING SUMMARY",
        line,
        (
            f"{'SECTOR':<20} "
            f"{'TOTAL':>5} "
            f"{'VOL':>4} "
            f"{'ATR':>4} "
            f"{'WEAK_TR':>7} "
            f"{'WEAK_MOM':>8} "
            f"{'READ':<8}"
        ),
    ]

    if not rows:
        lines.append("No sector warnings.")
        return lines

    for item in rows:
        read = str(item["read"])
        lines.append(
            f"{_fmt_sector(item['sector'], 20):<20} "
            f"{int(item['assets']):>5} "
            f"{int(item['vol_high']):>4} "
            f"{int(item['atr_high']):>4} "
            f"{int(item['weak_trend']):>7} "
            f"{int(item['weak_momentum']):>8} "
            f"{colorize(f'{read:<8}', read)}"
        )

    return lines


def _render_operational_summary(payload: dict[str, Any]) -> list[str]:
    summary = payload.get("summary", {})
    worst = [_fmt_sector(item, 18) for item in summary.get("worst_sectors", [])]
    volatile = [_fmt_sector(item, 18) for item in summary.get("volatile_sectors", [])]
    return format_kv_section(
        "SUMMARY",
        [
            ("warnings_assets", summary.get("warnings_assets", payload.get("warning_count", 0))),
            ("dominant_problem", summary.get("dominant_problem", "-")),
            ("worst_sectors", ", ".join(worst) or "-"),
            ("volatile_sectors", ", ".join(volatile) or "-"),
            ("best_relative", summary.get("best_relative_sector", "-")),
        ],
        label_width=18,
    ).splitlines()


def _render_warnings_by_asset(payload: dict[str, Any]) -> list[str]:
    line = muted_line()
    lines = [
        "WARNINGS BY ASSET",
        line,
        (
            f"{'TICKER':<8} "
            f"{'SECTOR':<16} "
            f"{'VOL':>7} "
            f"{'ATR':>7} "
            f"{'TREND':>7} "
            f"{'MOM':>7} "
            f"{'WARNINGS'}"
        ),
    ]

    warned = [item for item in payload['diagnostics'] if item['codes']]

    if not warned:
        lines.append("No asset warnings.")
    else:
        for item in warned:
            lines.append(
                f"{item['ticker']:<8} "
                f"{_fmt_sector(item['sector'], 16):<16} "
                f"{color_metric(item['volatility_pct'], 'vol', width=7)} "
                f"{color_metric(item['atr_pct'], 'atr', width=7)} "
                f"{color_metric(item['trend_score'], 'trend', width=7)} "
                f"{color_metric(item['momentum_score'], 'mom', width=7)} "
                f"{item['label']}"
            )

    return lines


def _render_universe_diagnose(payload: dict[str, Any], *, details: bool = False) -> str:
    concentration = payload["sector_concentration"]
    lines = [
        format_kv_section(
            "PYMERCATOR UNIVERSE DIAGNOSE",
            [
                ("file", payload["path"]),
                ("policy", payload["policy"]),
                ("assets", payload["assets"]),
                ("status", payload["data_status"], payload["data_status"]),
                ("warnings", payload["warning_count"]),
            ],
            label_width=20,
        ),
        "",
        format_kv_section(
            "COUNTS",
            [
                ("liquidity_low", payload["liquidity_low"]),
                ("vol_high", payload["volatility_high"]),
                ("atr_high", payload["atr_high"]),
                ("weak_trend", payload["weak_trend"]),
                ("weak_momentum", payload["weak_momentum"]),
                ("missing_plan", payload["missing_trade_plan"]),
            ],
            label_width=20,
        ),
        "",
    ]

    lines.extend(_render_sector_warning_summary(payload))
    lines.extend(["", *_render_operational_summary(payload)])
    lines.extend(
        [
            "",
            format_kv_section(
                "SECTOR CONCENTRATION",
                [
                    ("status", concentration["status"], concentration["status"]),
                    ("top_sector", _fmt_sector(concentration["top_sector"], 20)),
                    ("top_count", concentration["top_sector_count"]),
                    ("top_pct", f"{concentration['top_sector_pct']:.2f}%"),
                ],
                label_width=20,
            ),
        ]
    )

    if details:
        lines.append("")
        lines.extend(_render_warnings_by_asset(payload))

    return "\n".join(lines)


def _render_universe_build(payload: dict[str, Any]) -> str:
    line = "-" * 100
    lines = [
        "PYMERCATOR UNIVERSE BUILD",
        line,
        f"{'PRICES DIR':<20} {payload['prices_dir']}",
        f"{'TICKERS FILE':<20} {payload.get('tickers_file') or '-'}",
        f"{'OUTPUT':<20} {payload['output']}",
        f"{'ASSETS':<20} {payload['asset_count']}",
        f"{'ERRORS':<20} {payload['error_count']}",
        "",
        "ASSETS",
        line,
    ]

    lines.append(
        f"{'TICKER':<8} "
        f"{'SECTOR':<24} "
        f"{'CLOSE':>9} "
        f"{'TREND':>8} "
        f"{'MOM':>8} "
        f"{'VOL':>8} "
        f"{'ATR':>8} "
        f"{'NEWS':>8}"
    )
    lines.append(line)

    for asset in payload['assets']:
        lines.append(
            f"{asset['ticker']:<8} "
            f"{asset['sector']:<24} "
            f"{asset['last_close']:>9.2f} "
            f"{color_metric(asset['trend_score'], 'trend', width=8, precision=2)} "
            f"{color_metric(asset['momentum_score'], 'mom', width=8, precision=2)} "
            f"{color_metric(asset['volatility_pct'], 'vol', width=8, precision=2)} "
            f"{color_metric(asset['atr_pct'], 'atr', width=8, precision=2)} "
            f"{asset.get('news_score', 50.0):>8.2f}"
        )

    if payload['errors']:
        lines.append("")
        lines.append("ERRORS")
        lines.append(line)

        for error in payload['errors']:
            lines.append(f"{error['file']} error={error['error']}")

    return "\n".join(lines)


def run_universe_command(args: Any) -> int:
    if args.universe_command == 'check':
        payload = validate_universe_csv(args.file)

        if getattr(args, 'json', False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_render_universe_check(payload))

        return 0 if payload['valid'] else 1

    if args.universe_command == 'summary':
        payload = summarize_universe_csv(args.file)

        if getattr(args, 'json', False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_render_universe_summary(payload))

        return 0

    if args.universe_command == 'template':
        write_universe_template(args.output)
        print(f"Universe template written to: {args.output}")
        return 0

    if args.universe_command == 'build':
        payload = build_universe_csv_from_prices(
            prices_dir=args.prices_dir,
            output=args.output,
            sentiment_dir=getattr(args, 'sentiment_dir', '') or None,
            tickers_file=getattr(args, 'tickers_file', '') or None,
        )

        if getattr(args, 'json', False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_render_universe_build(payload))

        return 0 if payload['error_count'] == 0 and payload['asset_count'] > 0 else 1

    if args.universe_command == 'diagnose':
        payload = diagnose_universe_csv(
            path=args.file,
            policy_path=args.policy,
        )

        if getattr(args, 'json', False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(
                _render_universe_diagnose(
                    payload,
                    details=getattr(args, 'details', False),
                )
            )

        return 0 if payload['data_status'] in {'PASS', 'PASS_WITH_WARNINGS'} else 1

    raise ValueError(f"Unknown universe command: {args.universe_command}")
