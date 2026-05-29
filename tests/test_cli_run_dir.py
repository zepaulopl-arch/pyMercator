from pathlib import Path

from pymercator.cli import main


def test_daily_cli_run_dir_creates_timestamped_txt_and_json(tmp_path: Path):
    run_base = tmp_path / "daily_runs"

    exit_code = main(
        [
            "daily",
            "--universe",
            "data/universes/ibov_sample.csv",
            "--headline-risk",
            "ACTIVE",
            "--headline-tags",
            "IRAN,OIL,WAR",
            "--profile",
            "AGR",
            "--run-dir",
            str(run_base),
        ]
    )

    assert exit_code == 0
    assert run_base.exists()

    run_dirs = [path for path in run_base.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1

    report_txt = run_dirs[0] / "report.txt"
    report_json = run_dirs[0] / "report.json"

    assert report_txt.exists()
    assert report_json.exists()

    txt = report_txt.read_text(encoding="utf-8")
    json_text = report_json.read_text(encoding="utf-8")

    assert "PYMERCATOR DAILY OPERATIONAL REPORT" in txt
    assert "WATCH_ONLY" in txt
    assert '"posture": "WATCH_ONLY"' in json_text
    assert '"decision_codes"' in json_text
