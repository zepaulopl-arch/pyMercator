from pathlib import Path

from pymercator.cli import main


def test_indices_prices_check_command(tmp_path: Path, capsys):
    prices_dir = tmp_path / "indices"
    prices_dir.mkdir()

    (prices_dir / "^BVSP.csv").write_text(
        "date,open,high,low,close,volume\n"
        "2025-01-02,100,101,99,100.5,1000\n"
        "2025-01-03,101,102,100,101.5,1200\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "indices",
            "prices-check",
            "--prices-dir",
            str(prices_dir),
        ]
    )

    assert exit_code == 0

    captured = capsys.readouterr()
    assert "PYMERCATOR INDICES PRICES CHECK" in captured.out
    assert "VALID FILES" in captured.out
    assert "^BVSP.csv" in captured.out
