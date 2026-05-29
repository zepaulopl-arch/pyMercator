from pathlib import Path

from pymercator.indices_catalog import (
    validate_indices_catalog,
    write_indices_catalog,
)
from pymercator.legacy_indices import migrate_legacy_indices_catalog


def test_write_and_validate_indices_catalog(tmp_path: Path):
    output = tmp_path / "indices_catalog.json"

    result = write_indices_catalog(
        output=output,
        indices=[
            {
                "name": "IBOV",
                "symbol": "^BVSP",
                "provider": "yfinance",
                "category": "equity",
            }
        ],
    )

    validation = validate_indices_catalog(output)

    assert result["valid"] is True
    assert validation["valid"] is True
    assert validation["count"] == 1


def test_migrate_legacy_indices_catalog_from_yaml(tmp_path: Path):
    legacy = tmp_path / "legacy"
    catalog_dir = legacy / "config" / "indices"
    output = tmp_path / "indices_catalog.json"

    catalog_dir.mkdir(parents=True)
    (catalog_dir / "catalog.yaml").write_text(
        """
indices:
  ibov:
    name: IBOV
    symbol: ^BVSP
    provider: yfinance
    category: equity
  dolar:
    name: DXY
    symbol: DX-Y.NYB
    provider: yfinance
    category: currency
""",
        encoding="utf-8",
    )

    result = migrate_legacy_indices_catalog(
        legacy_path=legacy,
        output=output,
    )

    assert result["valid"] is True
    assert result["count"] == 2
    assert output.exists()

def test_migrate_legacy_indices_ignores_metadata_fields(tmp_path: Path):
    legacy = tmp_path / "legacy"
    catalog_dir = legacy / "config" / "indices"
    output = tmp_path / "indices_catalog.json"

    catalog_dir.mkdir(parents=True)
    (catalog_dir / "catalog.yaml").write_text(
        """
indices:
  ibov:
    label: Ibovespa
    role: benchmark_market
    provider: yfinance
    validation_status: pending_provider_validation
    yahoo_ticker: ^BVSP
  brent:
    label: Brent crude oil futures
    role: commodity_oil
    provider: yfinance
    yahoo_ticker: BZ=F
  dolar:
    label: USD/BRL
    role: fx
    provider: yfinance
    yahoo_ticker: USDBRL=X
""",
        encoding="utf-8",
    )

    result = migrate_legacy_indices_catalog(
        legacy_path=legacy,
        output=output,
    )

    symbols = {item["symbol"] for item in result["indices"]}
    names = {item["name"] for item in result["indices"]}

    assert result["valid"] is True
    assert result["count"] == 3
    assert symbols == {"^BVSP", "BZ=F", "USDBRL=X"}
    assert "provider" not in names
    assert "role" not in names
    assert "validation_status" not in names
    assert "yfinance" not in symbols
    assert "benchmark_market" not in symbols

