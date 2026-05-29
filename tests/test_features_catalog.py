from pathlib import Path

from pymercator.features_catalog import (
    migrate_legacy_features_catalog,
    validate_features_catalog,
    write_features_catalog,
)


def test_write_features_catalog_creates_valid_catalog(tmp_path: Path):
    output = tmp_path / "features_catalog.json"

    payload = write_features_catalog(output=output)

    assert output.exists()
    assert payload["valid"] is True
    assert payload["features"] >= 5
    assert payload["enabled"] >= 5


def test_validate_features_catalog_rejects_duplicate_names(tmp_path: Path):
    output = tmp_path / "features_catalog.json"

    output.write_text(
        """
{
  "features": [
    {"name": "return_1d", "group": "price"},
    {"name": "return_1d", "group": "price"}
  ]
}
""",
        encoding="utf-8",
    )

    payload = validate_features_catalog(output)

    assert payload["valid"] is False
    assert "duplicated name return_1d" in "\\n".join(payload["errors"])


def test_migrate_legacy_features_catalog_writes_output(tmp_path: Path):
    legacy = tmp_path / "legacy"
    config = legacy / "config"
    output = tmp_path / "features_catalog.json"

    config.mkdir(parents=True)
    (config / "features.yaml").write_text(
        "features:\\n  - return_1d\\n",
        encoding="utf-8",
    )

    payload = migrate_legacy_features_catalog(
        legacy_path=legacy,
        output=output,
    )

    assert payload["valid"] is True
    assert payload["source_file"].endswith("features.yaml")
    assert output.exists()
