from pathlib import Path

from pymercator.cli import main
from pymercator.data.prices_csv import write_price_rows_csv


def _write_price_file(path: Path) -> None:
    rows = []

    for index in range(80):
        close = 20.0 + index * 0.1
        rows.append(
            {
                "date": (
                    f"2025-01-{(index % 28) + 1:02d}"
                    if index < 28
                    else f"2025-02-{(index % 28) + 1:02d}"
                ),
                "open": round(close - 0.1, 2),
                "high": round(close + 0.2, 2),
                "low": round(close - 0.2, 2),
                "close": round(close, 2),
                "volume": 2000000 + index * 1000,
            }
        )

    write_price_rows_csv(path, rows)


def test_universe_build_command_creates_output_csv(tmp_path: Path, capsys):
    prices_dir = tmp_path / "prices"
    output = tmp_path / "universe.csv"
    prices_dir.mkdir()

    _write_price_file(prices_dir / "PRIO3.SA.csv")

    exit_code = main(
        [
            "universe",
            "build",
            "--prices-dir",
            str(prices_dir),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert output.exists()

    captured = capsys.readouterr()
    assert "PYMERCATOR UNIVERSE BUILD" in captured.out
    assert "PRIO3" in captured.out
