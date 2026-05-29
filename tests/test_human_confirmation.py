import json
from pathlib import Path

from pymercator.human_confirmation import register_human_confirmation


def _write_pack(pack: Path) -> None:
    scenario = pack / "03_active_agr"
    scenario.mkdir(parents=True)

    (pack / "00_manifest.json").write_text(
        json.dumps(
            {
                "created_at": "2026-01-01T10:00:00",
                "files": ["00_manifest.json"],
            }
        ),
        encoding="utf-8",
    )
    (pack / "00_manifest.txt").write_text(
        "PYMERCATOR SCENARIO PACK MANIFEST\n",
        encoding="utf-8",
    )
    (scenario / "report.json").write_text(
        json.dumps(
            {
                "decisions": [
                    {
                        "asset": {"ticker": "PETR4"},
                        "permission": {"status": "WATCH"},
                        "decision_label": "CTX_LOW",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_register_human_confirmation_writes_files_and_manifest(tmp_path: Path):
    pack = tmp_path / "pack"
    _write_pack(pack)

    payload = register_human_confirmation(
        pack=pack,
        ticker="PETR4",
        decision="REJECTED",
        notes="manual block",
        operator="test",
    )

    assert payload["human_decision"] == "REJECTED"
    assert payload["found_in_pack"] is True
    assert payload["execution_mode"] == "ANALYSIS_ONLY"

    json_path = pack / "00_human_confirmations.json"
    txt_path = pack / "00_human_confirmations.txt"
    manifest_path = pack / "00_manifest.json"

    assert json_path.exists()
    assert txt_path.exists()

    confirmations = json.loads(json_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert len(confirmations) == 1
    assert confirmations[0]["ticker"] == "PETR4"
    assert manifest["human_confirmations"] == 1
    assert "00_human_confirmations.json" in manifest["files"]
