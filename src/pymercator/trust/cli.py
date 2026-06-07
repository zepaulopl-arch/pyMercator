from __future__ import annotations

import argparse

from .report import build_trust_report, print_trust_report


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pymercator trust")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("report", help="Mostra painel de confianÃ§a operacional")

    args = parser.parse_args(argv)

    if args.command == "report":
        result = build_trust_report()
        print_trust_report(result)
        return None

    parser.error(f"comando desconhecido: {args.command}")


if __name__ == "__main__":
    main()
