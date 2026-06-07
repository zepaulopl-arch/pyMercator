from __future__ import annotations

import argparse

from .audit import audit
from .registry import summary, list_features
from .importance import importance
from .selection import canonical


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pymercator features")
    sub = parser.add_subparsers(dest="command", required=True)

    p_summary = sub.add_parser("summary", help="Resumo do registry de features")
    p_summary.add_argument("--dataset", default=None, help="Dataset CSV de features")

    p_list = sub.add_parser("list", help="Lista features registradas")
    p_list.add_argument("--dataset", default=None, help="Dataset CSV de features")

    p_audit = sub.add_parser("audit", help="Auditoria de qualidade das features")
    p_audit.add_argument("--dataset", default=None, help="Dataset CSV de features")

    p_importance = sub.add_parser("importance", help="Ranking de importancia das features")
    p_importance.add_argument("--limit", type=int, default=40, help="Numero de linhas exibidas")
    p_importance.add_argument("--raw", action="store_true", help="Mostra importance sem filtro canonico")

    p_canonical = sub.add_parser("canonical", help="Lista canonica sem aliases duplicados")
    p_canonical.add_argument("--dataset", default=None, help="Dataset CSV de features")
    p_canonical.add_argument("--limit", type=int, default=120, help="Numero de linhas exibidas")

    args = parser.parse_args(argv)

    if args.command == "summary":
        summary(args)
        return None

    if args.command == "list":
        list_features(args)
        return None

    if args.command == "audit":
        audit(args)
        return None

    if args.command == "importance":
        importance(args)
        return None

    if args.command == "canonical":
        canonical(args)
        return None

    parser.error(f"comando desconhecido: {args.command}")


if __name__ == "__main__":
    main()
