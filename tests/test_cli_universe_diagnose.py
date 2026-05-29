from pathlib import Path

from pymercator.cli import main
from pymercator.data.universe_csv import write_universe_template


def test_universe_diagnose_command_prints_report(tmp_path: Path, capsys):
    universe = tmp_path / "template.csv"
    write_universe_template(universe)

    exit_code = main(
        [
            "universe",
            "diagnose",
            "--file",
            str(universe),
        ]
    )

    assert exit_code in {0, 1}

    captured = capsys.readouterr()
    assert "PYMERCATOR UNIVERSE DIAGNOSE" in captured.out
    assert "DATA STATUS" in captured.out
    assert "SECTOR CONCENTRATION" in captured.out
