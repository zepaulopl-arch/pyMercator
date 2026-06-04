import json
from pathlib import Path

from pymercator.position_actions import build_position_actions
from pymercator.position_actions_config import load_position_actions_config

from test_position_actions import _decision, _report


def test_position_actions_config_loads_project_file():
    config = load_position_actions_config("config/position_actions.json")

    assert config["schema_version"] == "position_actions_config.v1"
    assert config["exit"]["take_profit_pct"] == 8.0
    assert config["short"]["observational_only"] is True
    assert config["short"]["block_without_borrow_data"] is True


def test_invalid_position_actions_config_falls_back_safely(tmp_path: Path):
    source = tmp_path / "position_actions.json"
    source.write_text('{"schema_version": "wrong"}', encoding="utf-8")

    config = load_position_actions_config(source)

    assert config["schema_version"] == "position_actions_config.v1"
    assert config["config_status"] == "DEFAULT"
    assert "unsupported" in config["config_warning"]


def test_stop_loss_threshold_is_configurable(tmp_path: Path):
    config = load_position_actions_config("config/position_actions.json")
    config["exit"]["stop_loss_pct"] = -10.0
    config_path = tmp_path / "position_actions.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    report = _report((_decision("ABCD3", trend=40.0, momentum=40.0, last_close=95.0, stop=90.0),))
    positions = tmp_path / "positions.csv"
    positions.write_text(
        "ticker,side,qty,avg_price,entry_date\nABCD3,LONG,100,100,2026-05-10\n",
        encoding="utf-8",
    )

    payload = build_position_actions(
        report,
        positions_path=positions,
        config_path=config_path,
    )

    assert payload["exit_book"]["rows"][0]["action"] != "STOP_LOSS"
    assert payload["config"]["status"] == "OK"
