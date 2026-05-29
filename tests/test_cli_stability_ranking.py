import json
from pathlib import Path

from pymercator.cli import main


def test_scenario_pack_creates_stability_ranking_outputs(tmp_path: Path):
    run_base = tmp_path / "scenario_runs"

    exit_code = main(
        [
            "scenario-pack",
            "--universe",
            "data/universes/ibov_sample.csv",
            "--headline-tags",
            "IRAN,OIL,WAR",
            "--run-dir",
            str(run_base),
        ]
    )

    assert exit_code == 0

    pack_dir = next(path for path in run_base.iterdir() if path.is_dir())

    stability_txt = pack_dir / "00_stability_ranking.txt"
    stability_json = pack_dir / "00_stability_ranking.json"
    summary_json = pack_dir / "00_pack_summary.json"

    assert stability_txt.exists()
    assert stability_json.exists()
    assert summary_json.exists()

    text = stability_txt.read_text(encoding="utf-8")
    assert "PYMERCATOR STABILITY RANKING" in text
    assert "PRIO3" in text

    rows = json.loads(stability_json.read_text(encoding="utf-8"))
    assert len(rows) > 0

    prio3 = next(row for row in rows if row["ticker"] == "PRIO3")
    assert prio3["survived"] >= 3
    assert prio3["watch"] >= 1
    assert prio3["blocked"] >= 1
    assert "REGIME_DENY" in prio3["codes"]

    summary = json.loads(summary_json.read_text(encoding="utf-8"))
    assert "stability_ranking" in summary
    assert len(summary["stability_ranking"]) == len(rows)
