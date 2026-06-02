from datetime import date, timedelta
from pathlib import Path

from pymercator.cli import main
from pymercator.data.prices_csv import write_price_rows_csv


def _write_asset_price_file(path: Path) -> None:
    rows = []

    for index in range(80):
        close = 30.0 + index * 0.1
        rows.append(
            {
                "date": (date(2025, 1, 2) + timedelta(days=index)).isoformat(),
                "open": round(close - 0.1, 2),
                "high": round(close + 0.2, 2),
                "low": round(close - 0.2, 2),
                "close": round(close, 2),
                "volume": 3000000 + index * 1000,
            }
        )

    write_price_rows_csv(path, rows)


def _write_index_price(path: Path) -> None:
    lines = ["date,open,high,low,close,volume"]

    for index in range(30):
        value = 100.0 + index
        day = (date(2025, 1, 2) + timedelta(days=index)).isoformat()
        lines.append(f"{day},{value},{value},{value},{value},1000")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_daily_auto_command_with_existing_indices(tmp_path: Path, capsys):
    indices_catalog = tmp_path / "indices_catalog.json"
    indices_dir = tmp_path / "indices"
    context_output = tmp_path / "market_context_auto.json"
    prices_dir = tmp_path / "prices"
    tickers_file = tmp_path / "tickers.csv"
    universe_output = tmp_path / "ibov_live.csv"
    feature_matrix_output = tmp_path / "latest_feature_matrix.csv"
    prediction_dataset_output = tmp_path / "latest_prediction_dataset.csv"
    prediction_evaluation_output = tmp_path / "latest_evaluation.json"
    run_dir = tmp_path / "scenario_runs"

    indices_dir.mkdir()
    prices_dir.mkdir()

    _write_index_price(indices_dir / "^BVSP.csv")
    _write_index_price(indices_dir / "BZ=F.csv")
    _write_index_price(indices_dir / "USDBRL=X.csv")
    _write_asset_price_file(prices_dir / "PRIO3.SA.csv")

    indices_catalog.write_text(
        '{"indices": []}',
        encoding="utf-8",
    )

    tickers_file.write_text(
        "ticker,sector\nPRIO3.SA,energy\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "daily-auto",
            "--indices-catalog",
            str(indices_catalog),
            "--indices-dir",
            str(indices_dir),
            "--context-output",
            str(context_output),
            "--tickers-file",
            str(tickers_file),
            "--prices-dir",
            str(prices_dir),
            "--universe-output",
            str(universe_output),
            "--feature-matrix-output",
            str(feature_matrix_output),
            "--prediction-dataset-output",
            str(prediction_dataset_output),
            "--prediction-evaluation-output",
            str(prediction_evaluation_output),
            "--run-dir",
            str(run_dir),
            "--skip-indices-fetch",
            "--skip-asset-fetch",
        ]
    )

    assert exit_code == 0
    assert context_output.exists()

    captured = capsys.readouterr()
    assert "PYMERCATOR DAILY AUTO SUMMARY" in captured.out
    assert "AUTO CONTEXT" in captured.out
    assert "REAL PACK" in captured.out
