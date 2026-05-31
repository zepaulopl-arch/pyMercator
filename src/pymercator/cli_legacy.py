from __future__ import annotations

import json
from typing import Any

from pymercator.features_catalog import migrate_legacy_features_catalog
from pymercator.legacy_classification import write_legacy_classification
from pymercator.legacy_indices import migrate_legacy_indices_catalog
from pymercator.legacy_inventory import write_legacy_inventory
from pymercator.legacy_universe import write_legacy_universe_ticker_list
from pymercator.sentiment_store import migrate_legacy_sentiment


def run_legacy_command(args: Any) -> int:
    if args.legacy_command == "classify":
        payload = write_legacy_classification(
            inventory_path=args.inventory,
            output_dir=args.output,
        )

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR LEGACY CLASSIFY")
            print("-" * 100)
            print(f"{'INVENTORY':<20} {payload['inventory_path']}")
            print(f"{'OUTPUT DIR':<20} {payload['output_dir']}")
            print(f"{'FILES':<20} {payload['file_count']}")
            print(f"{'TXT':<20} {payload['txt_path']}")
            print(f"{'JSON':<20} {payload['json_path']}")
            print("")
            print("DECISIONS")
            print("-" * 100)
            for decision, count in payload['decision_counts'].items():
                print(f"{decision:<20} {count}")

        return 0

    if args.legacy_command == "migrate-sentiment":
        payload = migrate_legacy_sentiment(
            legacy_path=args.legacy_path,
            source_dir=args.source_dir,
            output=args.output,
        )

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR LEGACY SENTIMENT MIGRATION")
            print("-" * 100)
            print(f"{'LEGACY PATH':<20} {payload['legacy_path']}")
            print(f"{'SOURCE DIR':<20} {payload['source_dir']}")
            print(f"{'OUTPUT':<20} {payload['output']}")
            print(f"{'COPIED':<20} {payload['copied']}")
            print(f"{'VALID FILES':<20} {payload['valid_files']}")
            print(f"{'INVALID FILES':<20} {payload['invalid_files']}")
            print(f"{'TICKERS':<20} {payload['tickers']}")

        return 0 if payload['copied'] > 0 and payload['invalid_files'] == 0 else 1

    if args.legacy_command == "migrate-features":
        payload = migrate_legacy_features_catalog(
            legacy_path=args.legacy_path,
            output=args.output,
        )

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR LEGACY FEATURES MIGRATION")
            print("-" * 100)
            print(f"{'LEGACY PATH':<20} {payload['legacy_path']}")
            print(f"{'SOURCE FILE':<20} {payload['source_file'] or '-'}")
            print(f"{'OUTPUT':<20} {payload['output']}")
            print(f"{'VALID':<20} {payload['valid']}")
            print(f"{'FEATURES':<20} {payload['features']}")
            print(f"{'ENABLED':<20} {payload['enabled']}")
            print(f"{'REQUIRED':<20} {payload['required']}")

        return 0 if payload['valid'] else 1

    if args.legacy_command == "migrate-indices":
        payload = migrate_legacy_indices_catalog(
            legacy_path=args.legacy_path,
            catalog_file=args.catalog_file,
            output=args.output,
        )

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR LEGACY INDICES MIGRATION")
            print("-" * 100)
            print(f"{'LEGACY PATH':<22} {payload['legacy_path']}")
            print(f"{'CATALOG YAML':<22} {payload['catalog_path']}")
            print(f"{'OUTPUT':<22} {payload['output']}")
            print(f"{'INDICES':<22} {payload['count']}")
            print(f"{'VALID':<22} {payload['valid']}")

        return 0 if payload['valid'] and payload['count'] > 0 else 1

    if args.legacy_command == "migrate-universe":
        payload = write_legacy_universe_ticker_list(
            legacy_path=args.legacy_path,
            assets_file=args.assets_file,
            universe_file=args.universe_file,
            output=args.output,
        )

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR LEGACY UNIVERSE MIGRATION")
            print("-" * 100)
            print(f"{'LEGACY PATH':<22} {payload['legacy_path']}")
            print(f"{'ASSETS YAML':<22} {payload['assets_path']}")
            print(f"{'UNIVERSE YAML':<22} {payload['universe_path']}")
            print(f"{'OUTPUT':<22} {payload['output']}")
            print(f"{'ASSETS FOUND':<22} {payload['assets_found']}")
            print(f"{'UNIVERSE TICKERS':<22} {payload['universe_tickers_found']}")
            print(f"{'ROWS':<22} {payload['rows']}")
            print(f"{'UNKNOWN SECTORS':<22} {payload['unknown_sector_count']}")
            print(f"{'VALID':<22} {payload['valid']}")

        return 0 if payload['valid'] and payload['rows'] > 0 else 1

    if args.legacy_command == "scan":
        payload = write_legacy_inventory(
            legacy_path=args.path,
            output_dir=args.output,
        )

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR LEGACY SCAN")
            print("-" * 100)
            print(f"{'LEGACY PATH':<20} {payload['legacy_path']}")
            print(f"{'OUTPUT DIR':<20} {payload['output_dir']}")
            print(f"{'FILES':<20} {payload['file_count']}")
            print(f"{'PYTHON FILES':<20} {payload['python_files']}")
            print(f"{'DATA FILES':<20} {payload['data_files']}")
            print(f"{'LARGE FILES':<20} {payload['large_files_count']}")
            print(f"{'TXT':<20} {payload['txt_path']}")
            print(f"{'JSON':<20} {payload['json_path']}")

        return 0

    raise ValueError(f"Unknown legacy command: {args.legacy_command}")
