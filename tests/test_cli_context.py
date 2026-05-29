from pathlib import Path

from pymercator.cli import main


def test_context_template_and_check_commands(tmp_path: Path, capsys):
    output = tmp_path / "market_context.json"

    template_exit = main(
        [
            "context",
            "template",
            "--output",
            str(output),
        ]
    )

    assert template_exit == 0
    assert output.exists()

    check_exit = main(
        [
            "context",
            "check",
            "--file",
            str(output),
        ]
    )

    assert check_exit == 0

    captured = capsys.readouterr()
    assert "Market context template written to:" in captured.out
    assert "PYMERCATOR MARKET CONTEXT CHECK" in captured.out
    assert "VALID" in captured.out
    assert "True" in captured.out
