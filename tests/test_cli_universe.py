from pathlib import Path

from pymercator.cli import main


def test_universe_check_command_accepts_sample(capsys):
    exit_code = main(
        [
            "universe",
            "check",
            "--file",
            "data/universes/ibov_sample.csv",
        ]
    )

    assert exit_code == 0

    captured = capsys.readouterr()
    assert "PYMERCATOR UNIVERSE CHECK" in captured.out
    assert "VALID" in captured.out
    assert "True" in captured.out


def test_universe_summary_command_prints_summary(capsys):
    exit_code = main(
        [
            "universe",
            "summary",
            "--file",
            "data/universes/ibov_sample.csv",
        ]
    )

    assert exit_code == 0

    captured = capsys.readouterr()
    assert "PYMERCATOR UNIVERSE SUMMARY" in captured.out
    assert "SECTORS" in captured.out
    assert "TOP VOLUME" in captured.out


def test_universe_template_command_creates_file(tmp_path: Path, capsys):
    output = tmp_path / "template.csv"

    exit_code = main(
        [
            "universe",
            "template",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert output.exists()

    captured = capsys.readouterr()
    assert "Universe template written to:" in captured.out
