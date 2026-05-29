from pathlib import Path

from pymercator.cli import main


def test_legacy_scan_command_writes_inventory(tmp_path: Path, capsys):
    legacy = tmp_path / "legacy"
    output = tmp_path / "inventory"
    legacy.mkdir()

    (legacy / "predict_model.py").write_text(
        "def predict():\n    return 1\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "legacy",
            "scan",
            "--path",
            str(legacy),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert (output / "legacy_inventory.txt").exists()
    assert (output / "legacy_inventory.json").exists()

    captured = capsys.readouterr()
    assert "PYMERCATOR LEGACY SCAN" in captured.out
    assert "PYTHON FILES" in captured.out
