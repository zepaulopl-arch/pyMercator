from datetime import datetime
from pathlib import Path
from typing import Any

from pymercator.execution_policy import load_execution_policy
from pymercator.manifest import (
    append_manifest_txt_section,
    load_json,
    update_manifest_files,
    write_json,
)

VALID_HUMAN_DECISIONS = {
    "APPROVED",
    "REJECTED",
    "WATCH",
    "SKIPPED",
}


def _load_json(path: Path, default: Any) -> Any:
    return load_json(path, default)


def _write_json(path: Path, payload: Any) -> None:
    write_json(path, payload)


def _find_ticker_in_pack(pack_dir: Path, ticker: str) -> dict[str, Any]:
    ticker_upper = ticker.strip().upper()

    matches: list[dict[str, Any]] = []

    for report_path in sorted(pack_dir.glob("*/report.json")):
        payload = _load_json(report_path, {})

        for decision in payload.get("decisions", []):
            asset = decision.get("asset", {})
            asset_ticker = str(asset.get("ticker", "")).upper()

            if asset_ticker == ticker_upper:
                matches.append(
                    {
                        "scenario": report_path.parent.name,
                        "ticker": asset_ticker,
                        "permission_status": decision.get(
                            "permission",
                            {},
                        ).get("status", "-"),
                        "decision_label": decision.get("decision_label", "-"),
                        "report_path": str(report_path),
                    }
                )

    return {
        "found": bool(matches),
        "matches": matches,
    }


def _render_confirmations(confirmations: list[dict[str, Any]]) -> str:
    line = "-" * 118
    lines = [
        "PYMERCATOR HUMAN CONFIRMATIONS",
        line,
        f"{'COUNT':<18} {len(confirmations)}",
        "",
        "CONFIRMATIONS",
        line,
    ]

    if not confirmations:
        lines.append("-")
        return "\n".join(lines)

    for item in confirmations:
        lines.append(
            f"{item['created_at']:<20} "
            f"{item['ticker']:<8} "
            f"{item['human_decision']:<10} "
            f"found={str(item['found_in_pack']):<5} "
            f"notes={item['notes'] or '-'}"
        )

    return "\n".join(lines)


def _update_manifest(pack_dir: Path, confirmation_count: int) -> None:
    manifest_path = pack_dir / "00_manifest.json"

    manifest = _load_json(manifest_path, {})
    update_manifest_files(
        manifest,
        (
            "00_human_confirmations.json",
            "00_human_confirmations.txt",
        ),
    )

    manifest.update(
        {
            "human_confirmations": confirmation_count,
            "human_confirmation_file": "00_human_confirmations.json",
        }
    )

    _write_json(manifest_path, manifest)
    append_manifest_txt_section(
        pack_dir,
        "HUMAN CONFIRMATION",
        [
            f"{'CONFIRMATIONS':<18} {confirmation_count}",
            f"{'FILE':<18} 00_human_confirmations.json",
        ],
    )


def register_human_confirmation(
    *,
    pack: str | Path,
    ticker: str,
    decision: str,
    notes: str = "",
    operator: str = "manual",
    execution_policy_path: str | Path = "config/execution_policy.json",
) -> dict[str, Any]:
    pack_dir = Path(pack)

    if not pack_dir.exists():
        raise FileNotFoundError(f"Pack directory not found: {pack_dir}")

    decision_upper = decision.strip().upper()
    if decision_upper not in VALID_HUMAN_DECISIONS:
        available = ", ".join(sorted(VALID_HUMAN_DECISIONS))
        raise ValueError(
            f"Invalid human decision: {decision}. Available: {available}"
        )

    ticker_upper = ticker.strip().upper()
    if not ticker_upper:
        raise ValueError("Ticker is required")

    execution_policy = load_execution_policy(execution_policy_path)
    lookup = _find_ticker_in_pack(pack_dir, ticker_upper)

    confirmations_path = pack_dir / "00_human_confirmations.json"
    confirmations_txt_path = pack_dir / "00_human_confirmations.txt"

    confirmations = _load_json(confirmations_path, [])

    record = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "pack": str(pack_dir),
        "ticker": ticker_upper,
        "human_decision": decision_upper,
        "notes": notes,
        "operator": operator,
        "found_in_pack": lookup["found"],
        "matches": lookup["matches"],
        "execution_mode": execution_policy["execution_mode"],
        "allow_order_routing": execution_policy["allow_order_routing"],
        "require_human_confirmation": execution_policy[
            "require_human_confirmation"
        ],
    }

    confirmations.append(record)

    _write_json(confirmations_path, confirmations)
    confirmations_txt_path.write_text(
        _render_confirmations(confirmations),
        encoding="utf-8",
    )

    _update_manifest(pack_dir, len(confirmations))

    return {
        "pack": str(pack_dir),
        "ticker": ticker_upper,
        "human_decision": decision_upper,
        "notes": notes,
        "operator": operator,
        "found_in_pack": lookup["found"],
        "matches": lookup["matches"],
        "confirmation_count": len(confirmations),
        "json_path": str(confirmations_path),
        "txt_path": str(confirmations_txt_path),
        "execution_mode": execution_policy["execution_mode"],
        "allow_order_routing": execution_policy["allow_order_routing"],
        "require_human_confirmation": execution_policy[
            "require_human_confirmation"
        ],
    }
