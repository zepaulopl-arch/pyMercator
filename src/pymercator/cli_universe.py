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
    line = "-" * 100
    lines = [
        "PYMERCATOR UNIVERSE SUMMARY",
        line,
        f"{'FILE':<20} {payload['path']}",
        f"{'ASSETS':<20} {payload['assets']}",
        f"{'AVG VOLUME BRL':<20} {payload['avg_volume_brl']:.2f}",
        f"{'AVG TREND':<20} {payload['avg_trend_score']:.2f}",
        f"{'AVG MOMENTUM':<20} {payload['avg_momentum_score']:.2f}",
        f"{'AVG VOLATILITY':<20} {payload['avg_volatility_pct']:.2f}",
        "",
        "SECTORS",
        line,
    ]

    for sector, count in payload['sectors'].items():
        lines.append(f"{sector:<20} {count}")

    lines.append("")
    lines.append("TOP VOLUME")
    lines.append(line)

    for item in payload['top_volume']:
        lines.append(
            f"{item['ticker']:<8} "
            f"{item['sector']:<12} "
            f"{item['avg_volume_brl']:>14.2f}"
        )

    return "\n".join(lines)


def _render_universe_diagnose(payload: dict[str, Any]) -> str:
    line = "-" * 100
    lines = [
        "PYMERCATOR UNIVERSE DIAGNOSE",
        line,
        f"{'FILE':<22} {payload['path']}",
        f"{'POLICY':<22} {payload['policy']}",
        f"{'ASSETS':<22} {payload['assets']}",
        f"{'MIN ASSETS':<22} {payload['min_assets']}",
        f"{'DATA STATUS':<22} {payload['data_status']}",
        f"{'ASSET COUNT':<22} {payload['asset_count_status']}",
        f"{'WARNINGS':<22} {payload['warning_count']}",
        "",
        "COUNTS",
        line,
        f"{'LIQUIDITY LOW':<22} {payload['liquidity_low']}",
        f"{'VOLATILITY HIGH':<22} {payload['volatility_high']}",
        f"{'ATR HIGH':<22} {payload['atr_high']}",
        f"{'WEAK TREND':<22} {payload['weak_trend']}",
        f"{'WEAK MOMENTUM':<22} {payload['weak_momentum']}",
        f"{'MISSING TRADE PLAN':<22} {payload['missing_trade_plan']}",
        "",
        "SECTOR CONCENTRATION",
        line,
        f"{'STATUS':<22} {payload['sector_concentration']['status']}",
        f"{'TOP SECTOR':<22} {payload['sector_concentration']['top_sector']}",
        f"{'TOP COUNT':<22} {payload['sector_concentration']['top_sector_count']}",
        f"{'TOP PCT':<22} {payload['sector_concentration']['top_sector_pct']:.2f}%",
        "",
        "WARNINGS BY ASSET",
        line,
    ]

    warned = [item for item in payload['diagnostics'] if item['codes']]

    if not warned:
        lines.append("No asset warnings.")
    else:
        for item in warned:
            lines.append(
                f"{item['ticker']:<8} "
                f"{item['sector']:<12} "
                f"vol={item['volatility_pct']:<6} "
                f"atr={item['atr_pct']:<6} "
                f"trend={item['trend_score']:<6} "
                f"mom={item['momentum_score']:<6} "
                f"{item['label']}"
            )

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
            f"{asset['trend_score']:>8.2f} "
            f"{asset['momentum_score']:>8.2f} "
            f"{asset['volatility_pct']:>8.2f} "
            f"{asset['atr_pct']:>8.2f} "
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
            print(_render_universe_diagnose(payload))

        return 0 if payload['data_status'] in {'PASS', 'PASS_WITH_WARNINGS'} else 1

    raise ValueError(f"Unknown universe command: {args.universe_command}")
