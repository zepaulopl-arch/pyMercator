from __future__ import annotations

import argparse

from .audit import build_train_audit, print_train_audit
from .compare import build_compare, print_compare
from .history import print_history


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pymercator train")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("audit", help="Audita o ultimo treino")

    p_compare = sub.add_parser("compare", help="Compara historico de treinos")
    p_compare.add_argument("--limit", type=int, default=10)

    p_history = sub.add_parser("history", help="Mostra historico de auditorias de treino")
    p_history.add_argument("--limit", type=int, default=20)

    args = parser.parse_args(argv)

    if args.command == "audit":
        result = build_train_audit(record=True)
        print_train_audit(result)
        return None

    if args.command == "compare":
        result = build_compare(limit=args.limit)
        print_compare(result)
        return None

    if args.command == "history":
        print_history(limit=args.limit)
        return None

    parser.error(f"comando desconhecido: {args.command}")


if __name__ == "__main__":
    main()
