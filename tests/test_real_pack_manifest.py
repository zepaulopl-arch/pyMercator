import json
from datetime import date, timedelta
from pathlib import Path

from pymercator.data.prices_csv import write_price_rows_csv
from pymercator.real_run import run_real_pack


def _write_price_file(path: Path) -> None:
    rows = []

    for index in range(80):
        close = 20.0 + index * 0.1
        rows.append(
            {
                "date": (date(2025, 1, 2) + timedelta(days=index)).isoformat(),
                "open": round(close - 0.1, 2),
                "high": round(close + 0.2, 2),
                "low": round(close - 0.2, 2),
                "close": round(close, 2),
                "volume": 2000000 + index * 1000,
            }
        )

    write_price_rows_csv(path, rows)


def test_real_pack_updates_manifest_with_real_pack_metadata(tmp_path: Path):
    prices_dir = tmp_path / "prices"
    tickers_file = tmp_path / "tickers.csv"
    universe_output = tmp_path / "universe.csv"
    run_dir = tmp_path / "scenario_runs"

    prices_dir.mkdir()
    _write_price_file(prices_dir / "PRIO3.SA.csv")

    tickers_file.write_text(
        "ticker,sector\nPRIO3.SA,CustomOil\n",
        encoding="utf-8",
    )

    payload = run_real_pack(
        tickers_file=str(tickers_file),
        start="2025-01-01",
        prices_dir=str(prices_dir),
        universe_output=str(universe_output),
        run_dir=str(run_dir),
        headline_tags=["IRAN", "OIL", "WAR"],
        skip_fetch=True,
    )

    pack_dir = Path(payload["pack_dir"])
    manifest_path = pack_dir / "00_manifest.json"
    manifest_txt_path = pack_dir / "00_manifest.txt"

    assert manifest_path.exists()
    assert manifest_txt_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_txt = manifest_txt_path.read_text(encoding="utf-8")

    assert manifest["source_command"] == "real-pack"
    assert manifest["real_pack"] is True
    assert manifest["tickers_file"] == str(tickers_file)
    assert manifest["prices_dir"] == str(prices_dir)
    assert manifest["universe_output"] == str(universe_output)
    assert manifest["skip_fetch"] is True
    assert manifest["prices_valid_files"] == 1
    assert manifest["universe_assets"] == 1
    assert "diagnosis_status" in manifest
    assert "00_real_pack_summary.txt" in manifest["files"]
    assert "00_real_pack_summary.json" in manifest["files"]
    assert "REAL PACK" in manifest_txt
