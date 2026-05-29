import json
from pathlib import Path

from pymercator.cli import main


def test_legacy_classify_command_writes_outputs(tmp_path: Path, capsys):
    inventory = tmp_path / "legacy_inventory.json"
    output = tmp_path / "inventory"

    payload = {
        "root": "C:/legacy",
        "files": [
            {
                "path": "config/assets/ibov_assets.yaml",
                "extension": ".yaml",
                "size_bytes": 100,
                "categories": ["assets"],
                "content_hints": [],
            }
        ],
    }

    inventory.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = main(
        [
            "legacy",
            "classify",
            "--inventory",
            str(inventory),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert (output / "legacy_classification.txt").exists()
    assert (output / "legacy_classification.json").exists()

    captured = capsys.readouterr()
    assert "PYMERCATOR LEGACY CLASSIFY" in captured.out
    assert "MIGRAR_AGORA" in captured.out
