import json
from pathlib import Path

from pymercator.cli import main


def test_packs_command_lists_generated_scenario_packs(tmp_path: Path, capsys):
    run_base = tmp_path / "scenario_runs"

    create_exit = main(
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

    assert create_exit == 0

    list_exit = main(
        [
            "packs",
            "--run-dir",
            str(run_base),
        ]
    )

    assert list_exit == 0

    captured = capsys.readouterr()
    assert "PYMERCATOR PACK INDEX" in captured.out
    assert "PRIO3" in captured.out
    assert "SCEN" in captured.out
    assert "WATCH_ONLY" in captured.out


def test_packs_command_can_print_json(tmp_path: Path, capsys):
    run_base = tmp_path / "scenario_runs"

    create_exit = main(
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

    assert create_exit == 0

    list_exit = main(
        [
            "packs",
            "--run-dir",
            str(run_base),
            "--json",
        ]
    )

    assert list_exit == 0

    captured = capsys.readouterr()
    json_start = captured.out.find("[")
    payload = json.loads(captured.out[json_start:])

    assert len(payload) == 1
    assert payload[0]["universe_name"] == "IBOV"
    assert payload[0]["top_ticker"] == "PRIO3"
    assert payload[0]["type"] == "SCEN"
