from pathlib import Path

from pymercator.cli import main


def _write_prices(path: Path, closes: list[float]) -> None:
    lines = ["date,open,high,low,close,volume"]

    for index, close in enumerate(closes, start=1):
        lines.append(
            f"2025-01-{index:02d},{close},{close},{close},{close},1000"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_context_auto_command_writes_context_file(tmp_path: Path, capsys):
    indices = tmp_path / "indices"
    output = tmp_path / "market_context_auto.json"
    indices.mkdir()

    _write_prices(indices / "^BVSP.csv", [100 + i for i in range(30)])
    _write_prices(indices / "BZ=F.csv", [70.0 for _ in range(30)])
    _write_prices(indices / "USDBRL=X.csv", [5.0 for _ in range(30)])

    exit_code = main(
        [
            "context",
            "auto",
            "--indices-dir",
            str(indices),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert output.exists()

    captured = capsys.readouterr()
    assert "PYMERCATOR MARKET CONTEXT AUTO" in captured.out
    assert "RISK_ON" in captured.out
