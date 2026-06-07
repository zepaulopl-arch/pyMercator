from __future__ import annotations

import argparse
import subprocess
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pymercator train run")
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--autotune", action="store_true")
    parser.add_argument("--no-autotune", action="store_true")
    parser.add_argument("--extra", nargs=argparse.REMAINDER)

    args = parser.parse_args(argv)

    # Etapa 7: no train behavior change. Delegate to existing train.
    cmd = [sys.executable, "-m", "pymercator", "train"]

    if args.details:
        cmd.append("--details")

    if args.autotune and not args.no_autotune:
        cmd.append("--autotune")

    if args.extra:
        cmd.extend(args.extra)

    raise SystemExit(subprocess.call(cmd))
