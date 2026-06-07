from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


HISTORY_DIR = Path("storage/training")
HISTORY_FILE = HISTORY_DIR / "train_history.csv"
LATEST_AUDIT_JSON = HISTORY_DIR / "latest_train_audit.json"


HISTORY_COLUMNS = [
    "run_id",
    "created_at",
    "features_used",
    "raw_features",
    "canonical_features",
    "removed_features",
    "engines_used",
    "engines",
    "horizons",
    "meta_model",
    "observer",
    "D5_edge",
    "D20_edge",
    "D60_edge",
    "global_edge",
    "quality",
    "status",
    "verdict",
    "most_reliable_horizon",
    "best_engine",
    "least_bad_engine",
    "tradability",
]


def now_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_history_dir() -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def append_history(row: dict[str, Any]) -> None:
    ensure_history_dir()

    exists = HISTORY_FILE.exists()

    with HISTORY_FILE.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=HISTORY_COLUMNS)

        if not exists:
            writer.writeheader()

        clean = {key: row.get(key, "") for key in HISTORY_COLUMNS}
        writer.writerow(clean)


def read_history(limit: int | None = None) -> list[dict[str, str]]:
    if not HISTORY_FILE.exists():
        return []

    with HISTORY_FILE.open("r", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    if limit is not None and limit > 0:
        return rows[-limit:]

    return rows


def save_latest_audit(payload: dict[str, Any]) -> None:
    ensure_history_dir()
    LATEST_AUDIT_JSON.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def print_history(limit: int = 20) -> None:
    rows = read_history(limit=limit)

    print("AURUM TRAIN HISTORY")
    print("-" * 80)

    if not rows:
        print("none")
        return

    print(
        f"{'run_id':<16} "
        f"{'features':>8} "
        f"{'eng':>4} "
        f"{'D5_edge':>8} "
        f"{'D20_edge':>8} "
        f"{'D60_edge':>8} "
        f"{'global':>8} "
        f"{'quality':<8} "
        f"{'status':<12} "
        f"{'verdict':<10}"
    )

    for row in rows:
        print(
            f"{row.get('run_id', '-'):<16} "
            f"{row.get('features_used', '-'):>8} "
            f"{row.get('engines_used', '-'):>4} "
            f"{row.get('D5_edge', '-'):>8} "
            f"{row.get('D20_edge', '-'):>8} "
            f"{row.get('D60_edge', '-'):>8} "
            f"{row.get('global_edge', '-'):>8} "
            f"{row.get('quality', '-'):<8} "
            f"{row.get('status', '-'):<12} "
            f"{row.get('verdict', '-'):<10}"
        )
