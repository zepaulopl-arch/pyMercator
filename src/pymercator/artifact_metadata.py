from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


def _git_value(args: list[str], *, cwd: str | Path = ".") -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def git_metadata(*, cwd: str | Path = ".") -> dict[str, Any]:
    branch = _git_value(["branch", "--show-current"], cwd=cwd)
    commit = _git_value(["rev-parse", "--short", "HEAD"], cwd=cwd)
    dirty = bool(_git_value(["status", "--porcelain"], cwd=cwd))
    return {
        "branch": branch or "UNKNOWN",
        "commit": commit or "UNKNOWN",
        "dirty": dirty,
    }


def python_metadata() -> dict[str, str]:
    return {
        "executable": sys.executable,
        "version": platform.python_version(),
    }


def artifact_metadata(*, cwd: str | Path = ".") -> dict[str, Any]:
    return {
        "python": python_metadata(),
        "git": git_metadata(cwd=cwd),
    }
