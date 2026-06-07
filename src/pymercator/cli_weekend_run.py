from __future__ import annotations

import argparse
import subprocess
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pymercator weekend run")
    parser.add_argument("--details", action="store_true", default=True)
    parser.add_argument("--no-details", action="store_true")
    parser.add_argument("--autotune", action="store_true", default=True)
    parser.add_argument("--no-autotune", action="store_true")
    parser.add_argument("--extra", nargs=argparse.REMAINDER)

    args = parser.parse_args(argv)

    # Etapa 7: weekend is an orchestration wrapper, not new training logic.
    cmd = [sys.executable, "-m", "pymercator", "train"]

    if args.details and not args.no_details:
        cmd.append("--details")

    if args.autotune and not args.no_autotune:
        cmd.append("--autotune")

    if args.extra:
        cmd.extend(args.extra)

    raise SystemExit(subprocess.call(cmd))
