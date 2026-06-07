from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def _ensure_review_report_bridge(run_dir: Path, profile: str) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)

    profile_upper = str(profile or "CON").upper()
    expected = run_dir / f"report_{profile_upper}.json"

    if expected.exists():
        return expected

    candidates = [
        Path("storage/reports/latest_daily_report.json"),
        Path("storage/runs/latest/latest_daily_report.json"),
        Path("storage/runs/latest/report.json"),
        Path("storage/reports/latest_report.json"),
    ]

    for candidate in candidates:
        if candidate.exists():
            shutil.copyfile(candidate, expected)
            return expected

    raise FileNotFoundError(
        "No compatible report JSON found. Expected one of: "
        + ", ".join(str(x) for x in candidates)
    )


def _run_age_minutes(path: Path) -> float | None:
    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime)
        return max(0.0, (datetime.now() - modified).total_seconds() / 60.0)
    except Exception:
        return None


def _write_review_status(
    *,
    status: str,
    mode: str,
    profile: str,
    run_dir: Path,
    report: Path,
    reason: str,
    age_minutes: float | None,
) -> None:
    out = Path("storage/reports")
    out.mkdir(parents=True, exist_ok=True)

    payload = {
        "status": status,
        "mode": str(mode),
        "profile": str(profile),
        "run_dir": str(run_dir),
        "report": str(report),
        "reason": reason,
        "age_minutes": age_minutes,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }

    (out / "latest_review.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pymercator review run")
    parser.add_argument("--profile", default="CON")
    parser.add_argument("--list", default="IBOV")
    parser.add_argument("--run-dir", default="storage/runs/latest")
    parser.add_argument("--capital", default=None)
    parser.add_argument("--mode", default="observation", choices=["observation", "all"])
    parser.add_argument("--min-age-minutes", type=float, default=60.0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--extra", nargs=argparse.REMAINDER)

    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)

    if not run_dir.exists():
        print(f"ERROR: run-dir not found: {run_dir}")
        print("Run signal first:")
        print("  python -m pymercator signal run --profile CON --top 10 --list IBOV")
        raise SystemExit(2)

    try:
        bridged = _ensure_review_report_bridge(run_dir, args.profile)
        print(f"REVIEW BRIDGE | report {bridged}")
    except Exception as exc:
        print(f"ERROR: could not prepare review report bridge: {exc}")
        print("Run signal first:")
        print("  python -m pymercator signal run --profile CON --top 10 --list IBOV")
        raise SystemExit(2)

    age = _run_age_minutes(bridged)

    if not args.force and age is not None and age < float(args.min_age_minutes):
        reason = (
            f"report too recent for mark-to-market review "
            f"({age:.1f} min < {float(args.min_age_minutes):.1f} min)"
        )

        print("AURUM MTM REVIEW")
        print("-" * 80)
        print("status             NOT_ELAPSED")
        print(f"reason             {reason}")
        print("read               radar was created too recently; PnL would be mostly zero")
        print("action             run review later, or use --force only for mechanical smoke test")

        _write_review_status(
            status="NOT_ELAPSED",
            mode=str(args.mode),
            profile=str(args.profile),
            run_dir=run_dir,
            report=bridged,
            reason=reason,
            age_minutes=age,
        )

        print("REVIEW STATUS | NOT_ELAPSED | storage/reports/latest_review.json")
        raise SystemExit(0)

    cmd = [
        sys.executable,
        "-m",
        "pymercator",
        "review",
        "--run-dir",
        str(run_dir),
        "--profile",
        str(args.profile),
        "--mode",
        str(args.mode),
    ]

    if args.capital is not None:
        cmd.extend(["--capital", str(args.capital)])

    if args.json:
        cmd.append("--json")

    if args.extra:
        cmd.extend(args.extra)

    result = subprocess.call(cmd)

    if result == 0:
        try:
            if args.force:
                status = "FORCED_SMOKE_TEST"
                reason = "review executed with --force; mechanical test only, not elapsed performance review"
            else:
                status = "OK"
                reason = "review executed on aged report"

            _write_review_status(
                status=status,
                mode=str(args.mode),
                profile=str(args.profile),
                run_dir=run_dir,
                report=bridged,
                reason=reason,
                age_minutes=age,
            )
            print(f"REVIEW STATUS | {status} | storage/reports/latest_review.json")
        except Exception as exc:
            print(f"REVIEW STATUS | WARN | could not write latest_review.json: {exc}")

    raise SystemExit(result)


if __name__ == "__main__":
    main()
