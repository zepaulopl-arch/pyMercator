from pathlib import Path

from pymercator.cli import main


def test_execution_template_and_check_commands(tmp_path: Path, capsys):
    output = tmp_path / "execution_policy.json"

    template_exit = main(
        [
            "execution",
            "template",
            "--output",
            str(output),
        ]
    )

    assert template_exit == 0
    assert output.exists()

    check_exit = main(
        [
            "execution",
            "check",
            "--file",
            str(output),
        ]
    )

    assert check_exit == 0

    captured = capsys.readouterr()
    assert "Execution policy template written to:" in captured.out
    assert "PYMERCATOR EXECUTION POLICY CHECK" in captured.out
    assert "ANALYSIS_ONLY" in captured.out
