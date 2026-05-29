from pathlib import Path

from pymercator.cli import main


def test_prices_tickers_template_and_check(tmp_path: Path, capsys):
    output = tmp_path / "ibov_tickers.csv"

    template_exit = main(
        [
            "prices",
            "tickers-template",
            "--output",
            str(output),
        ]
    )

    assert template_exit == 0
    assert output.exists()

    check_exit = main(
        [
            "prices",
            "tickers-check",
            "--file",
            str(output),
        ]
    )

    assert check_exit == 0

    captured = capsys.readouterr()
    assert "Ticker list template written to:" in captured.out
    assert "PYMERCATOR TICKER LIST CHECK" in captured.out
    assert "VALID" in captured.out
    assert "True" in captured.out
