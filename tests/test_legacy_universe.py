from pathlib import Path

from pymercator.data.ticker_list import validate_ticker_list_csv
from pymercator.legacy_universe import (
    load_legacy_universe,
    write_legacy_universe_ticker_list,
)


def test_load_legacy_universe_extracts_tickers_and_sectors(tmp_path: Path):
    legacy = tmp_path / "legacy"
    assets_dir = legacy / "config" / "assets"
    universes_dir = legacy / "config" / "universes"
    assets_dir.mkdir(parents=True)
    universes_dir.mkdir(parents=True)

    (assets_dir / "ibov_assets.yaml").write_text(
        """
assets:
  PETR4:
    sector: OilGas
  VALE3:
    sector: Mining
  ABEV3:
    sector: Consumer
""",
        encoding="utf-8",
    )

    (universes_dir / "ibov.yaml").write_text(
        """
tickers:
  - PETR4
  - VALE3
""",
        encoding="utf-8",
    )

    payload = load_legacy_universe(legacy_path=legacy)

    assert payload["assets_found"] == 3
    assert payload["universe_tickers_found"] == 2
    assert payload["row_count"] == 2
    assert {"ticker": "PETR4.SA", "sector": "OilGas"} in payload["rows"]
    assert {"ticker": "VALE3.SA", "sector": "Mining"} in payload["rows"]


def test_write_legacy_universe_ticker_list_creates_valid_csv(tmp_path: Path):
    legacy = tmp_path / "legacy"
    assets_dir = legacy / "config" / "assets"
    universes_dir = legacy / "config" / "universes"
    output = tmp_path / "ibov_tickers.csv"

    assets_dir.mkdir(parents=True)
    universes_dir.mkdir(parents=True)

    (assets_dir / "ibov_assets.yaml").write_text(
        """
assets:
  PETR4:
    sector: OilGas
  VALE3:
    sector: Mining
""",
        encoding="utf-8",
    )

    (universes_dir / "ibov.yaml").write_text(
        """
tickers:
  - PETR4.SA
  - VALE3.SA
""",
        encoding="utf-8",
    )

    payload = write_legacy_universe_ticker_list(
        legacy_path=legacy,
        output=output,
    )

    validation = validate_ticker_list_csv(output)

    assert payload["valid"] is True
    assert payload["rows"] == 2
    assert output.exists()
    assert validation["valid"] is True
