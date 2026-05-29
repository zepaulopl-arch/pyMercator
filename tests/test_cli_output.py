from pathlib import Path

from pymercator.cli import main


def test_daily_cli_writes_output_file(tmp_path: Path):
    output = tmp_path / "report.txt"

    exit_code = main(
        [
            "daily",
            "--universe",
            "data/universes/ibov_sample.csv",
            "--headline-risk",
            "ACTIVE",
            "--headline-tags",
            "IRAN,OIL",
            "--profile",
            "AGR",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert output.exists()

    text = output.read_text(encoding="utf-8")

    assert "PYMERCATOR DAILY OPERATIONAL REPORT" in text
    assert "1. MARKET REGIME" in text
    assert "2. UNIVERSE HEALTH" in text
    assert "3. ASSET RANKING" in text
    assert "6. HUMAN CONFIRMATION" in text
    assert "HEADLINE RISK" in text
    assert "ACTIVE" in text
