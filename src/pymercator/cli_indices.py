from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pymercator.indices_catalog import (
    render_indices_catalog,
    validate_indices_catalog,
)
from pymercator.indices_prices import (
    check_indices_prices_dir,
    fetch_indices_prices,
)


def run_indices_command(args: Any) -> int:
    if args.indices_command == "fetch":
        payload = fetch_indices_prices(
            catalog=args.catalog,
            start=args.start,
            end=args.end or None,
            output=args.output,
        )

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR INDICES FETCH")
            print("-" * 100)
            print(f"{'CATALOG':<20} {payload['catalog']}")
            print(f"{'OUTPUT DIR':<20} {payload['output']}")
            print(f"{'STATUS':<20} {payload['status']}")
            print(f"{'REQUESTED':<20} {payload['requested']}")
            print(f"{'FETCHED':<20} {payload['fetched']}")
            print(f"{'FAILED':<20} {payload['failed']}")
            print(f"{'REQUIRED FAILED':<20} {payload['required_failed']}")
            print(f"{'OPTIONAL FAILED':<20} {payload['optional_failed']}")
            print(f"{'SKIPPED':<20} {payload['skipped']}")
            print(f"{'START':<20} {payload['start']}")
            print(f"{'END':<20} {payload['end'] or '-'}")
            print("")
            print("RESULTS")
            print("-" * 100)

            for item in payload["results"]:
                print(
                    f"{item['symbol']:<14} "
                    f"{item['status']:<8} "
                    f"{item['rows']:>5} "
                    f"{item['start'] or '-':<10} "
                    f"{item['end'] or '-':<10} "
                    f"{item['path']}"
                )

        return 0 if payload["required_failed"] == 0 else 1

    if args.indices_command == "prices-check":
        payload = check_indices_prices_dir(args.prices_dir)

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR INDICES PRICES CHECK")
            print("-" * 100)
            print(f"{'PRICES DIR':<20} {payload['prices_dir']}")
            print(f"{'EXISTS':<20} {payload['exists']}")
            print(f"{'FILES':<20} {payload['files']}")
            print(f"{'VALID FILES':<20} {payload['valid_files']}")
            print(f"{'INVALID FILES':<20} {payload['invalid_files']}")
            print("")
            print("FILES")
            print("-" * 100)

            files = (
                payload.get("results")
                or payload.get("file_results")
                or payload.get("files_detail")
                or []
            )

            if not files:
                prices_path = Path(args.prices_dir)
                files = [
                    {
                        "file": item.name,
                        "status": "OK",
                        "rows": 0,
                        "start": "-",
                        "end": "-",
                    }
                    for item in sorted(prices_path.glob("*.csv"))
                ]

            for item in files:
                file_name = item.get("file") or item.get("path") or item.get("name") or "-"
                status = item.get("status") or ("OK" if item.get("valid") else "INVALID")

                print(
                    f"{file_name:<24} "
                    f"{status:<8} "
                    f"rows={item.get('rows', 0):<6} "
                    f"start={item.get('start', '-') or '-'} "
                    f"end={item.get('end', '-') or '-'}"
                )

        return 0 if payload["exists"] and payload["invalid_files"] == 0 else 1

    payload = validate_indices_catalog(args.file)

    if args.indices_command == "catalog":
        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_indices_catalog(payload))

        return 0 if payload["valid"] else 1

    if args.indices_command == "check":
        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR INDICES CATALOG CHECK")
            print("-" * 100)
            print(f"{'FILE':<20} {payload['path']}")
            print(f"{'VALID':<20} {payload['valid']}")
            print(f"{'INDICES':<20} {payload['count']}")

            if payload["errors"]:
                print("")
                print("ERRORS")
                print("-" * 100)
                for error in payload["errors"]:
                    print(f"- {error}")

        return 0 if payload["valid"] else 1

    raise ValueError(f"Unknown indices command: {args.indices_command}")
