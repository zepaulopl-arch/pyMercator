from pathlib import Path

from pymercator.cli import main


def test_legacy_migrate_indices_and_catalog_commands(tmp_path: Path, capsys):
    legacy = tmp_path / "legacy"
    catalog_dir = legacy / "config" / "indices"
    output = tmp_path / "indices_catalog.json"

    catalog_dir.mkdir(parents=True)
    (catalog_dir / "catalog.yaml").write_text(
        """
indices:
  ibov:
    name: IBOV
    symbol: ^BVSP
    provider: yfinance
    category: equity
""",
        encoding="utf-8",
    )

    migrate_exit = main(
        [
            "legacy",
            "migrate-indices",
            "--legacy-path",
            str(legacy),
            "--output",
            str(output),
        ]
    )

    assert migrate_exit == 0
    assert output.exists()

    check_exit = main(
        [
            "indices",
            "check",
            "--file",
            str(output),
        ]
    )

    assert check_exit == 0

    catalog_exit = main(
        [
            "indices",
            "catalog",
            "--file",
            str(output),
        ]
    )

    assert catalog_exit == 0

    captured = capsys.readouterr()
    assert "PYMERCATOR LEGACY INDICES MIGRATION" in captured.out
    assert "PYMERCATOR INDICES CATALOG CHECK" in captured.out
    assert "PYMERCATOR INDICES CATALOG" in captured.out
    assert "IBOV" in captured.out
