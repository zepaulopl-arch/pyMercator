from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pymercator.data.prices_csv import check_prices_dir
from pymercator.data.prices_yahoo import (
    fetch_yahoo_prices_from_ticker_file,
    fetch_yahoo_prices_to_dir,
)
from pymercator.data.ticker_list import (
    validate_ticker_list_csv,
    write_starter_ticker_list,
)


def _split_tags(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _render_ticker_list_check(payload: dict[str, Any]) -> str:
    line = "-" * 100
    lines = [
        "PYMERCATOR TICKER LIST CHECK",
        line,
        f"{'FILE':<20} {payload['path']}",
        f"{'VALID':<20} {payload['valid']}",
        f"{'ROWS':<20} {payload['rows']}",
        f"{'MISSING COLUMNS':<20} {', '.join(payload['missing_columns']) or '-'}",
        f"{'EXTRA COLUMNS':<20} {', '.join(payload['extra_columns']) or '-'}",
        f"{'DUPLICATES':<20} {', '.join(payload['duplicate_tickers']) or '-'}",
        f"{'ROW ERRORS':<20} {len(payload['row_errors'])}",
    ]

    if payload["row_errors"]:
        lines.append("")
        lines.append("ERRORS")
        lines.append(line)

        for error in payload["row_errors"][:20]:
            lines.append(
                f"line={error['line']} field={error['field']} error={error['error']}"
            )

    return "\n".join(lines)


def _render_prices_fetch(payload: dict[str, Any]) -> str:
    line = "-" * 100
    lines = [
        "PYMERCATOR PRICES FETCH",
        line,
        f"{'OUTPUT DIR':<20} {payload['output_dir']}",
        f"{'REQUESTED':<20} {payload['requested']}",
        f"{'FETCHED':<20} {payload['fetched']}",
        f"{'FAILED':<20} {payload['failed']}",
        f"{'START':<20} {payload['start']}",
        f"{'END':<20} {payload['end'] or '-'}",
        "",
        "RESULTS",
        line,
    ]

    for item in payload['results']:
        status = 'OK' if item['valid'] else 'FAILED'
        lines.append(
            f"{item['ticker']:<12} "
            f"{status:<8} "
            f"{item['rows']:>6} "
            f"{str(item['start_date'] or '-'):>10} "
            f"{str(item['end_date'] or '-'):>10} "
            f"{item['path']}"
        )

        if item['error']:
            lines.append(f"{'':<12} error={item['error']}")

    return "\n".join(lines)


def _render_prices_check(payload: dict[str, Any]) -> str:
    line = "-" * 100
    lines = [
        "PYMERCATOR PRICES CHECK",
        line,
        f"{'PRICES DIR':<20} {payload['prices_dir']}",
        f"{'EXISTS':<20} {payload['exists']}",
        f"{'FILES':<20} {payload['files']}",
        f"{'VALID FILES':<20} {payload['valid_files']}",
        f"{'INVALID FILES':<20} {payload['invalid_files']}",
        "",
        "FILES",
        line,
    ]

    for item in payload['results']:
        status = 'OK' if item.get('valid') else 'FAILED'
        lines.append(
            f"{Path(item['path']).name:<18} "
            f"{status:<8} "
            f"rows={item.get('rows', 0):<6} "
            f"start={item.get('start_date') or '-'} "
            f"end={item.get('end_date') or '-'}"
        )

        if item.get('error'):
            lines.append(f"{'':<18} error={item['error']}")

    return "\n".join(lines)


def run_prices_command(args: Any) -> int:
    if args.prices_command == 'fetch':
        payload = fetch_yahoo_prices_to_dir(
            tickers=_split_tags(args.tickers),
            start=args.start,
            end=args.end or None,
            output_dir=args.output,
        )

        if getattr(args, 'json', False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_render_prices_fetch(payload))

        return 0 if payload['required_failed'] == 0 else 1

    if args.prices_command == 'fetch-list':
        payload = fetch_yahoo_prices_from_ticker_file(
            tickers_file=args.tickers_file,
            start=args.start,
            end=args.end or None,
            output_dir=args.output,
        )

        if getattr(args, 'json', False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_render_prices_fetch(payload))

        return 0 if payload['required_failed'] == 0 else 1

    if args.prices_command == 'tickers-template':
        write_starter_ticker_list(args.output)
        print(f"Ticker list template written to: {args.output}")
        return 0

    if args.prices_command == 'tickers-check':
        payload = validate_ticker_list_csv(args.file)

        if getattr(args, 'json', False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_render_ticker_list_check(payload))

        return 0 if payload['valid'] else 1

    if args.prices_command == 'check':
        payload = check_prices_dir(args.prices_dir)

        if getattr(args, 'json', False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_render_prices_check(payload))

        if not payload['exists'] or payload['files'] == 0:
            return 1

        return 0 if payload['invalid_files'] == 0 else 1

    raise ValueError(f"Unknown prices command: {args.prices_command}")
