from pathlib import Path

from pymercator.cli import main


def test_features_check_command(tmp_path: Path, capsys):
    output = tmp_path / "features_catalog.json"

    output.write_text(
        """
{
  "features": [
    {
      "name": "return_1d",
      "group": "price",
      "enabled": true,
      "required": true,
      "description": "test"
    }
  ]
}
""",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "features",
            "check",
            "--file",
            str(output),
        ]
    )

    assert exit_code == 0

    captured = capsys.readouterr()
    assert "PYMERCATOR FEATURES CATALOG" in captured.out
    assert "return_1d" in captured.out


def test_legacy_migrate_features_command(tmp_path: Path, capsys):
    legacy = tmp_path / "legacy"
    config = legacy / "config"
    output = tmp_path / "features_catalog.json"

    config.mkdir(parents=True)
    (config / "features.yaml").write_text(
        "features:\\n  - return_1d\\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "legacy",
            "migrate-features",
            "--legacy-path",
            str(legacy),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert output.exists()

    captured = capsys.readouterr()
    assert "PYMERCATOR LEGACY FEATURES MIGRATION" in captured.out
    assert "FEATURES" in captured.out
