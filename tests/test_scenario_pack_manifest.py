import json
from pathlib import Path

from pymercator.scenario_pack import run_scenario_pack


def test_run_scenario_pack_creates_manifest_files(tmp_path: Path):
    pack_dir, _, _ = run_scenario_pack(
        universe_path="data/universes/ibov_sample.csv",
        universe_name="IBOV",
        headline_tags=["IRAN", "OIL", "WAR"],
        market_trend="CHOPPY",
        market_volatility="NORMAL",
        policy_path="config/policy.json",
        run_dir=str(tmp_path / "scenario_runs"),
        limit=20,
    )

    manifest_txt = pack_dir / "00_manifest.txt"
    manifest_json = pack_dir / "00_manifest.json"

    assert manifest_txt.exists()
    assert manifest_json.exists()

    text = manifest_txt.read_text(encoding="utf-8")
    payload = json.loads(manifest_json.read_text(encoding="utf-8"))

    assert "PYMERCATOR SCENARIO PACK MANIFEST" in text
    assert payload["command"] == "scenario-pack"
    assert payload["universe_name"] == "IBOV"
    assert payload["headline_tags"] == ["IRAN", "OIL", "WAR"]
    assert payload["scenario_count"] == 4
    assert "00_pack_summary.txt" in payload["files"]
    assert "00_stability_ranking.json" in payload["files"]
    assert "01_off_con/report.txt" in payload["files"]
