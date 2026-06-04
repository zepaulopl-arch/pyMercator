import json
from pathlib import Path

from pymercator.cli import main


def _write_observation_universe(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                (
                    "ticker,sector,last_close,avg_volume_brl,trend_score,"
                    "momentum_score,volatility_pct,atr_pct,liquidity_score,"
                    "quality_score,news_score,entry,stop,target"
                ),
                "MOMR3,materials,10,100000000,90,90,80,5,90,70,60,10,9,12",
                "STBL3,utilities,10,100000000,20,20,10,1,90,70,60,10,9,12",
                "WATC3,staples,10,100000000,55,45,20,2,90,70,60,10,9,12",
                "DANG3,financials,10,100000000,20,20,95,9,90,70,60,10,9,12",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_observe_generates_obs_index_for_all_assets(tmp_path: Path, capsys) -> None:
    universe = tmp_path / "universe.csv"
    _write_observation_universe(universe)

    exit_code = main(
        [
            "observe",
            "--list",
            "IBOV",
            "--universe",
            str(universe),
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "observe"
    assert payload["not_trade_signal"] is True
    assert len(payload["rows"]) == 4
    assert all(0 <= row["obs_index"] <= 100 for row in payload["rows"])
    assert payload["cluster"]["enabled"] is False
    assert payload["cluster"]["requested"] is False


def test_observe_classifies_momentum_high_risk_and_weak_assets(
    tmp_path: Path,
    capsys,
) -> None:
    universe = tmp_path / "universe.csv"
    _write_observation_universe(universe)

    main(["observe", "--universe", str(universe), "--json"])

    payload = json.loads(capsys.readouterr().out)
    rows = {row["ticker"]: row for row in payload["rows"]}
    assert rows["MOMR3"]["class"] == "MOM_HIGH_RISK"
    assert rows["STBL3"]["class"] in {"WEAK", "LOW_RISK_WEAK"}
    assert rows["DANG3"]["class"] == "DANGER"
    assert "STABLE" + "_WEAK" not in json.dumps(payload)


def test_observe_uses_renamed_favorable_class(tmp_path: Path, capsys) -> None:
    universe = tmp_path / "universe.csv"
    universe.write_text(
        "\n".join(
            [
                (
                    "ticker,sector,last_close,avg_volume_brl,trend_score,"
                    "momentum_score,volatility_pct,atr_pct,liquidity_score,"
                    "quality_score,news_score,entry,stop,target"
                ),
                "FAVR3,utilities,10,100000000,90,90,10,1,90,70,60,10,9,12",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    main(["observe", "--universe", str(universe), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["rows"][0]["class"] == "OBS_FAVORABLE"
    assert "OBS" + "_READY" not in json.dumps(payload)


def test_observe_renders_sector_summary(tmp_path: Path, capsys) -> None:
    universe = tmp_path / "universe.csv"
    _write_observation_universe(universe)

    exit_code = main(["observe", "--universe", str(universe)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "OBSERVATION INDEX" in output
    assert "SECTOR OBSERVATION" in output
    assert "materials" in output


def test_observe_weights_are_configurable(tmp_path: Path, capsys) -> None:
    universe = tmp_path / "universe.csv"
    config = tmp_path / "observation.json"
    _write_observation_universe(universe)
    config.write_text(
        json.dumps(
            {
                "weights": {
                    "trend": 1.0,
                    "momentum": 0.0,
                    "volatility_safety": 0.0,
                    "atr_safety": 0.0,
                },
                "risk_penalty": {"vol_high": 0, "atr_high": 0},
            }
        ),
        encoding="utf-8",
    )

    main(["observe", "--universe", str(universe), "--config", str(config), "--json"])

    payload = json.loads(capsys.readouterr().out)
    rows = {row["ticker"]: row for row in payload["rows"]}
    assert rows["MOMR3"]["obs_index"] == 90.0
    assert rows["STBL3"]["obs_index"] == 20.0


def test_observe_cluster_option_does_not_run_by_default(tmp_path: Path, capsys) -> None:
    universe = tmp_path / "universe.csv"
    _write_observation_universe(universe)

    main(["observe", "--universe", str(universe), "--cluster", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["cluster"]["requested"] is True
    assert payload["cluster"]["enabled"] is False


def test_observe_calibrate_writes_threshold_payload(tmp_path: Path, capsys) -> None:
    universe = tmp_path / "universe.csv"
    output = tmp_path / "observation_calibration.json"
    _write_observation_universe(universe)

    exit_code = main(
        [
            "observe",
            "calibrate",
            "--universe",
            str(universe),
            "--output",
            str(output),
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "observe_calibrate"
    assert payload["asset_count"] == 4
    assert payload["config_patch"]["thresholds"] == payload["thresholds"]
    assert output.exists()
