from pathlib import Path

from pymercator.cli import main


def test_legacy_migrate_universe_command_creates_ticker_csv(
    tmp_path: Path,
    capsys,
):
    legacy = tmp_path / "legacy"
    assets_dir = legacy / "config" / "assets"
    universes_dir = legacy / "config" / "universes"
    output = tmp_path / "ibov_tickers.csv"

    assets_dir.mkdir(parents=True)
    universes_dir.mkdir(parents=True)

    (assets_dir / "ibov_assets.yaml").write_text(
        """
assets:
  PRIO3:
    sector: OilGas
  GGBR4:
    sector: Steel
""",
        encoding="utf-8",
    )

    (universes_dir / "ibov.yaml").write_text(
        """
tickers:
  - PRIO3
  - GGBR4
""",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "legacy",
            "migrate-universe",
            "--legacy-path",
            str(legacy),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert output.exists()

    captured = capsys.readouterr()
    assert "PYMERCATOR LEGACY UNIVERSE MIGRATION" in captured.out
    assert "ROWS" in captured.out
    assert "2" in captured.out
