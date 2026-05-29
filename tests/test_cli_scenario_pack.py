import json
from pathlib import Path

from pymercator.cli import main


def test_scenario_pack_creates_all_expected_reports(tmp_path: Path):
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
    assert run_base.exists()

    pack_dirs = [path for path in run_base.iterdir() if path.is_dir()]
    assert len(pack_dirs) == 1

    pack_dir = pack_dirs[0]

    expected = [
        "01_off_con",
        "02_watch_bal",
        "03_active_agr",
        "04_extreme_agr",
    ]

    for name in expected:
        scenario_dir = pack_dir / name
        assert scenario_dir.exists()
        assert (scenario_dir / "report.txt").exists()
        assert (scenario_dir / "report.json").exists()

    assert (pack_dir / "00_pack_summary.txt").exists()
    assert (pack_dir / "00_pack_summary.json").exists()

    summary = json.loads((pack_dir / "00_pack_summary.json").read_text(encoding="utf-8"))

    assert len(summary["scenarios"]) == 4
    assert summary["scenarios"][0]["key"] == "01_off_con"
    assert summary["scenarios"][2]["headline_risk"] == "ACTIVE"
    assert summary["scenarios"][3]["headline_risk"] == "EXTREME"
