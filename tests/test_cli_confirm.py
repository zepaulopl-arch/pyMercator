import json
from pathlib import Path

from pymercator.cli import main


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
                        "asset": {"ticker": "VALE3"},
                        "permission": {"status": "WATCH"},
                        "decision_label": "CTX_LOW",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_confirm_command_registers_human_decision(tmp_path: Path, capsys):
    pack = tmp_path / "pack"
    _write_pack(pack)

    exit_code = main(
        [
            "confirm",
            "--pack",
            str(pack),
            "--ticker",
            "VALE3",
            "--decision",
            "WATCH",
            "--notes",
            "manual review",
            "--operator",
            "test",
        ]
    )

    assert exit_code == 0
    assert (pack / "00_human_confirmations.json").exists()

    captured = capsys.readouterr()
    assert "PYMERCATOR HUMAN CONFIRMATION" in captured.out
    assert "ANALYSIS_ONLY" in captured.out
    assert "VALE3" in captured.out
