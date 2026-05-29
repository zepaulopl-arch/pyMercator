from pathlib import Path

from pymercator.data.universe_csv import (
    load_universe_csv,
    summarize_universe_csv,
    validate_universe_csv,
    write_universe_template,
)


def test_validate_universe_csv_accepts_sample_file():
    payload = validate_universe_csv("data/universes/ibov_sample.csv")

    assert payload["valid"] is True
    assert payload["rows"] > 0
    assert payload["missing_columns"] == []
    assert payload["row_errors"] == []


def test_summarize_universe_csv_returns_sector_counts():
    payload = summarize_universe_csv("data/universes/ibov_sample.csv")

    assert payload["assets"] > 0
    assert "OilGas" in payload["sectors"]
    assert payload["avg_volume_brl"] > 0
    assert len(payload["top_volume"]) > 0


def test_write_universe_template_creates_valid_csv(tmp_path: Path):
    output = tmp_path / "template.csv"

    write_universe_template(output)

    assert output.exists()

    payload = validate_universe_csv(output)
    assets = load_universe_csv(output)

    assert payload["valid"] is True
    assert len(assets) == 2
