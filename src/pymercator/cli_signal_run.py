from __future__ import annotations

import argparse
import subprocess
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pymercator signal run")
    parser.add_argument("--profile", default="CON")
    parser.add_argument("--top", default="10")
    parser.add_argument("--list", default="IBOV")
    parser.add_argument("--basket", action="store_true")
    parser.add_argument("--no-basket", action="store_true")
    parser.add_argument("--extra", nargs=argparse.REMAINDER)

    args = parser.parse_args(argv)

    # Etapa 7: do not change signal behavior.
    # The legacy command is: python -m pymercator run
    # It accepts profile/list/basket, but not --top.
    # So signal run accepts --top for future API compatibility but does not pass it
    # until the legacy signal command supports it.
    cmd = [
        sys.executable,
        "-m",
        "pymercator",
        "run",
        "--profile",
        str(args.profile),
        "--list",
        str(args.list),
    ]

    if args.basket and not args.no_basket:
        cmd.append("--basket")

    if args.extra:
        cmd.extend(args.extra)

    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
