from pathlib import Path

from pymercator.scenario_pack import run_scenario_pack


def test_run_scenario_pack_module_creates_summary_and_stability(tmp_path: Path):
    pack_dir, summary_text, stability_text = run_scenario_pack(
        universe_path="data/universes/ibov_sample.csv",
        universe_name="IBOV",
        headline_tags=["IRAN", "OIL", "WAR"],
        market_trend="CHOPPY",
        market_volatility="NORMAL",
        policy_path="config/policy.json",
        run_dir=str(tmp_path / "scenario_runs"),
        limit=20,
    )

    assert pack_dir.exists()
    assert "PYMERCATOR SCENARIO PACK SUMMARY" in summary_text
    assert "PYMERCATOR STABILITY RANKING" in stability_text

    assert (pack_dir / "00_pack_summary.txt").exists()
    assert (pack_dir / "00_pack_summary.json").exists()
    assert (pack_dir / "00_stability_ranking.txt").exists()
    assert (pack_dir / "00_stability_ranking.json").exists()
