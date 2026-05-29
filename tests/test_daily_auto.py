from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from pymercator.daily_auto import run_daily_auto
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


def test_run_daily_auto_creates_context_and_pack(tmp_path: Path, monkeypatch):
    indices_catalog = tmp_path / "indices_catalog.json"
    indices_dir = tmp_path / "indices"
    context_output = tmp_path / "market_context_auto.json"
    feature_matrix_output = tmp_path / "latest_feature_matrix.csv"
    prices_dir = tmp_path / "prices"
    sentiment_dir = tmp_path / "sentiment"
    tickers_file = tmp_path / "tickers.csv"
    universe_output = tmp_path / "ibov_live.csv"
    run_dir = tmp_path / "scenario_runs"

    prices_dir.mkdir()
    sentiment_dir.mkdir()
    _write_asset_price_file(prices_dir / "PRIO3.SA.csv")

    (sentiment_dir / "PRIO3_SA_sentiment_daily.csv").write_text(
        "date,score,count\n"
        "2025-01-02,0.20,2\n"
        "2025-01-03,0.40,3\n",
        encoding="utf-8",
    )

    tickers_file.write_text(
        "ticker,sector\nPRIO3.SA,energy\n",
        encoding="utf-8",
    )

    indices_catalog.write_text(
        """
{
  "indices": [
    {
      "name": "Ibovespa",
      "symbol": "^BVSP",
      "provider": "yfinance",
      "category": "market",
      "description": "",
      "required": true,
      "enabled": true
    },
    {
      "name": "Brent",
      "symbol": "BZ=F",
      "provider": "yfinance",
      "category": "market",
      "description": "",
      "required": true,
      "enabled": true
    },
    {
      "name": "USD/BRL",
      "symbol": "USDBRL=X",
      "provider": "yfinance",
      "category": "market",
      "description": "",
      "required": true,
      "enabled": true
    }
  ]
}
""",
        encoding="utf-8",
    )

    def fake_download(symbol: str, start: str, end: str | None = None):
        base = {
            "^BVSP": 100.0,
            "BZ=F": 70.0,
            "USDBRL=X": 5.0,
        }[symbol]

        return pd.DataFrame(
            {
                "date": [
                    (date(2025, 1, 2) + timedelta(days=index)).isoformat()
                    for index in range(30)
                ],
                "open": [base + index for index in range(30)],
                "high": [base + index for index in range(30)],
                "low": [base + index for index in range(30)],
                "close": [base + index for index in range(30)],
                "volume": [1000 for _ in range(30)],
            }
        )

    monkeypatch.setattr("pymercator.indices_prices._download_yfinance", fake_download)

    payload = run_daily_auto(
        indices_catalog=str(indices_catalog),
        indices_start="2025-01-01",
        indices_dir=str(indices_dir),
        context_output=str(context_output),
        feature_matrix_output=str(feature_matrix_output),
        tickers_file=str(tickers_file),
        sentiment_dir=str(sentiment_dir),
        prices_dir=str(prices_dir),
        universe_output=str(universe_output),
        run_dir=str(run_dir),
        skip_asset_fetch=True,
        fetch_indices=True,
    )

    assert payload["status"] == "OK"
    assert context_output.exists()
    assert payload["indices_fetch"]["fetched"] == 3
    assert payload["real_pack"]["pack_dir"]
    assert feature_matrix_output.exists()
    assert payload["feature_matrix"]["rows"] == 1
    assert payload["feature_matrix"]["columns"] >= 3

    manifest = Path(payload["real_pack"]["pack_dir"]) / "00_manifest.json"
    assert '"feature_matrix"' in manifest.read_text(encoding="utf-8")

    pack_dir = Path(payload["real_pack"]["pack_dir"])
    universe_file = universe_output.read_text(encoding="utf-8")
    assert "65.0" in universe_file or "65.00" in universe_file
    assert pack_dir.exists()
