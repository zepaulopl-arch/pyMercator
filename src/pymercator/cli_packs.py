from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _pack_top_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    scenarios = summary.get("scenarios", [])

    if not scenarios:
        return {}

    active = next(
        (
            scenario
            for scenario in scenarios
            if scenario.get("key") == "03_active_agr"
        ),
        None,
    )

    selected = active or scenarios[0]
    top = selected.get("top", {})

    return {
        "scenario": selected.get("key", "-"),
        "ticker": top.get("ticker", "-"),
        "permission": top.get("permission", "-"),
        "label": top.get("decision_label", "-"),
    }


def _load_pack_index(run_dir: str, limit: int) -> list[dict[str, Any]]:
    base = Path(run_dir)

    if not base.exists():
        return []

    rows: list[dict[str, Any]] = []

    for pack_dir in sorted(
        [path for path in base.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ):
        manifest_path = pack_dir / "00_manifest.json"
        summary_path = pack_dir / "00_pack_summary.json"

        if not manifest_path.exists() or not summary_path.exists():
            continue

        manifest = _read_json(manifest_path)
        summary = _read_json(summary_path)
        top = _pack_top_from_summary(summary)

        scenarios = summary.get("scenarios", [])
        active = next(
            (
                scenario
                for scenario in scenarios
                if scenario.get("key") == "03_active_agr"
            ),
            scenarios[0] if scenarios else {},
        )

        is_real_pack = bool(manifest.get("real_pack", False))
        pack_type = "REAL" if is_real_pack else "SCEN"

        rows.append(
            {
                "pack": pack_dir.name,
                "path": str(pack_dir),
                "type": pack_type,
                "source_command": manifest.get("source_command", "scenario-pack"),
                "created_at": manifest.get(
                    "real_pack_created_at",
                    manifest.get("created_at", "-"),
                ),
                "universe_name": manifest.get("universe_name", "-"),
                "headline_tags": manifest.get("headline_tags", []),
                "market_trend": manifest.get("market_trend", "-"),
                "market_volatility": manifest.get("market_volatility", "-"),
                "active_posture": active.get("posture", "-"),
                "active_ready": active.get("ready", 0),
                "active_watch": active.get("watch", 0),
                "active_blocked": active.get("blocked", 0),
                "top_scenario": top.get("scenario", "-"),
                "top_ticker": top.get("ticker", "-"),
                "top_permission": top.get("permission", "-"),
                "top_label": top.get("label", "-"),
                "tickers_file": manifest.get("tickers_file", ""),
                "prices_dir": manifest.get("prices_dir", ""),
                "universe_output": manifest.get("universe_output", ""),
                "prices_valid_files": manifest.get("prices_valid_files", None),
                "universe_assets": manifest.get("universe_assets", None),
                "diagnosis_status": manifest.get("diagnosis_status", ""),
                "diagnosis_warnings": manifest.get("diagnosis_warnings", None),
            }
        )

        if len(rows) >= limit:
            break

    return rows


def _render_pack_index(rows: list[dict[str, Any]], run_dir: str) -> str:
    line = "-" * 118
    lines: list[str] = []

    lines.append("PYMERCATOR PACK INDEX")
    lines.append(line)
    lines.append(f"{'RUN DIR':<14} {run_dir}")
    lines.append(f"{'PACKS':<14} {len(rows)}")
    lines.append("")

    if not rows:
        lines.append("No scenario packs found.")
        return "\n".join(lines)

    lines.append(
        f"{'PACK':<16} "
        f"{'TYPE':<5} "
        f"{'CREATED_AT':<19} "
        f"{'ASSETS':>6} "
        f"{'STATUS':<18} "
        f"{'POSTURE':<12} "
        f"{'R/W/B':<9} "
        f"{'TOP':<6} "
        f"{'EXEC':<8} "
        f"{'LABEL':<20}"
    )
    lines.append(line)

    for row in rows:
        rwb = f"{row['active_ready']}/{row['active_watch']}/{row['active_blocked']}"

        label = str(row['top_label'])
        if len(label) > 20:
            label = label[:17] + "..."

        assets = row['universe_assets']
        assets_text = str(assets) if assets is not None else "-"

        status = row['diagnosis_status'] or "-"
        if len(status) > 18:
            status = status[:15] + "..."

        lines.append(
            f"{row['pack']:<16} "
            f"{row['type']:<5} "
            f"{row['created_at']:<19} "
            f"{assets_text:>6} "
            f"{status:<18} "
            f"{row['active_posture']:<12} "
            f"{rwb:<9} "
            f"{row['top_ticker']:<6} "
            f"{row['top_permission']:<8} "
            f"{label:<20}"
        )

    return "\n".join(lines)


def run_packs_command(args: Any) -> int:
    rows = _load_pack_index(args.run_dir, args.limit)

    if getattr(args, "json", False):
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    print(_render_pack_index(rows, args.run_dir))
    return 0
