from pathlib import Path

from pymercator.data.universe_csv import write_universe_template
from pymercator.data.universe_diagnostics import diagnose_universe_csv


def test_diagnose_universe_csv_returns_status_for_template(tmp_path: Path):
    universe = tmp_path / "template.csv"
    write_universe_template(universe)

    payload = diagnose_universe_csv(path=universe)

    assert payload["assets"] == 2
    assert payload["data_status"] in {
        "WARN_SMALL_UNIVERSE",
        "PASS_WITH_WARNINGS",
        "PASS",
    }
    assert "sector_concentration" in payload
    assert "diagnostics" in payload


def test_diagnose_universe_csv_flags_small_universe_for_template(tmp_path: Path):
    universe = tmp_path / "template.csv"
    write_universe_template(universe)

    payload = diagnose_universe_csv(path=universe)

    assert payload["asset_count_status"] == "TOO_SMALL"
    assert payload["assets"] < payload["min_assets"]
