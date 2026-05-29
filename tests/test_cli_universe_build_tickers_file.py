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


def test_universe_build_command_accepts_tickers_file(tmp_path: Path, capsys):
    prices_dir = tmp_path / "prices"
    output = tmp_path / "universe.csv"
    tickers = tmp_path / "tickers.csv"

    prices_dir.mkdir()
    _write_price_file(prices_dir / "PRIO3.SA.csv")

    tickers.write_text(
        "ticker,sector\nPRIO3.SA,CustomOil\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "universe",
            "build",
            "--prices-dir",
            str(prices_dir),
            "--tickers-file",
            str(tickers),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert output.exists()

    captured = capsys.readouterr()
    assert "PYMERCATOR UNIVERSE BUILD" in captured.out
    assert "TICKERS FILE" in captured.out
    assert "CustomOil" in output.read_text(encoding="utf-8")
