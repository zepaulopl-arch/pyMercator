from pathlib import Path

import pandas as pd

from pymercator.indices_prices import check_indices_prices_dir, fetch_indices_prices


def test_fetch_indices_prices_writes_price_csvs(tmp_path: Path, monkeypatch):
    catalog = tmp_path / "indices_catalog.json"
    output = tmp_path / "indices"

    catalog.write_text(
        '''
{
  "indices": [
    {
      "name": "Ibovespa",
      "symbol": "^BVSP",
      "provider": "yfinance",
      "category": "market",
      "description": ""
    }
  ]
}
''',
        encoding="utf-8",
    )

    def fake_download(symbol: str, start: str, end: str | None = None):
        return pd.DataFrame(
            {
                "date": ["2025-01-02", "2025-01-03"],
                "open": [100.0, 101.0],
                "high": [101.0, 102.0],
                "low": [99.0, 100.0],
                "close": [100.5, 101.5],
                "volume": [1000, 1200],
            }
        )

    monkeypatch.setattr("pymercator.indices_prices._download_yfinance", fake_download)

    payload = fetch_indices_prices(
        catalog=catalog,
        start="2025-01-01",
        output=output,
    )

    assert payload["requested"] == 1
    assert payload["fetched"] == 1
    assert payload["failed"] == 0
    assert (output / "^BVSP.csv").exists()


def test_check_indices_prices_dir_validates_written_files(tmp_path: Path):
    prices_dir = tmp_path / "indices"
    prices_dir.mkdir()

    (prices_dir / "^BVSP.csv").write_text(
        "date,open,high,low,close,volume\n"
        "2025-01-02,100,101,99,100.5,1000\n"
        "2025-01-03,101,102,100,101.5,1200\n",
        encoding="utf-8",
    )

    payload = check_indices_prices_dir(prices_dir)

    assert payload["exists"] is True
    assert payload["valid_files"] == 1
    assert payload["invalid_files"] == 0

def test_fetch_indices_prices_allows_optional_failure(tmp_path: Path, monkeypatch):
    catalog = tmp_path / "indices_catalog.json"
    output = tmp_path / "indices"

    catalog.write_text(
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
      "name": "Financial sector index",
      "symbol": "IFNC.SA",
      "provider": "yfinance",
      "category": "market",
      "description": "",
      "required": false,
      "enabled": true
    }
  ]
}
""",
        encoding="utf-8",
    )

    def fake_download(symbol: str, start: str, end: str | None = None):
        if symbol == "IFNC.SA":
            return pd.DataFrame()

        return pd.DataFrame(
            {
                "date": ["2025-01-02", "2025-01-03"],
                "open": [100.0, 101.0],
                "high": [101.0, 102.0],
                "low": [99.0, 100.0],
                "close": [100.5, 101.5],
                "volume": [1000, 1200],
            }
        )

    monkeypatch.setattr("pymercator.indices_prices._download_yfinance", fake_download)

    payload = fetch_indices_prices(
        catalog=catalog,
        start="2025-01-01",
        output=output,
    )

    assert payload["status"] == "OK_WITH_WARNINGS"
    assert payload["fetched"] == 1
    assert payload["failed"] == 1
    assert payload["required_failed"] == 0
    assert payload["optional_failed"] == 1

def test_fetch_indices_prices_sanitizes_incomplete_ohlc(tmp_path: Path, monkeypatch):
    catalog = tmp_path / "indices_catalog.json"
    output = tmp_path / "indices"

    catalog.write_text(
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
    }
  ]
}
""",
        encoding="utf-8",
    )

    def fake_download(symbol: str, start: str, end: str | None = None):
        return pd.DataFrame(
            {
                "date": ["2025-01-02", "2025-01-03"],
                "open": [100.0, 0.0],
                "high": [101.0, 0.0],
                "low": [99.0, 0.0],
                "close": [100.5, 101.5],
                "volume": [1000, 1200],
            }
        )

    monkeypatch.setattr("pymercator.indices_prices._download_yfinance", fake_download)

    payload = fetch_indices_prices(
        catalog=catalog,
        start="2025-01-01",
        output=output,
    )

    assert payload["status"] == "OK"

    content = (output / "^BVSP.csv").read_text(encoding="utf-8")
    assert "2025-01-03,101.5,101.5,101.5,101.5,1200" in content

