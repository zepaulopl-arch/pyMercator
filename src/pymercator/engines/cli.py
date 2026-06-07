from __future__ import annotations

import argparse

from .registry import print_engine_list
from .scoreboard import build_scoreboard, print_scoreboard
from .diagnostics import explain_engines


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pymercator engines")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="Lista engines registradas")
    sub.add_parser("scoreboard", help="Mostra desempenho por engine e horizonte")
    sub.add_parser("explain", help="Explica quais engines ajudam ou atrapalham")

    args = parser.parse_args(argv)

    if args.command == "list":
        print_engine_list()
        return None

    if args.command == "scoreboard":
        result = build_scoreboard()
        print_scoreboard(result)
        return None

    if args.command == "explain":
        explain_engines()
        return None

    parser.error(f"comando desconhecido: {args.command}")


if __name__ == "__main__":
    main()
