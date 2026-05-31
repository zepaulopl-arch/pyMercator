from pymercator.cli import main


def test_cli_diag_separates_libraries_from_prediction_engines(monkeypatch, capsys):
    import pymercator.legacy_prediction_engines as engines_mod

    monkeypatch.setattr(engines_mod, "SKLEARN_AVAILABLE", True)
    monkeypatch.setattr(engines_mod, "XGBOOST_AVAILABLE", False)
    monkeypatch.setattr(engines_mod, "CATBOOST_AVAILABLE", False)

    exit_code = main(["diag"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "PYMERCATOR DIAG" in output
    assert "PREDICTION CONFIG:" in output
    assert "- default_engine: multi_horizon_ridge" in output
    assert "- horizons: D5,D20,D60" in output
    assert "- base_engines: extratrees,randomforest,gradientboosting" in output
    assert "- meta_model: ridge" in output
    assert "- observer_mode: weighted" in output
    assert "LIBRARIES:" in output
    assert "- sklearn available: True" in output
    assert "PREDICTION ENGINES:" in output
    assert "- rolling_majority: available baseline" in output
    assert "- extratrees: available" in output
    assert "- randomforest: available" in output
    assert "- gradientboosting: available" in output
    assert "- ridge: available" in output
    assert "- ridge_ensemble: available per-horizon" in output
    assert "- multi_horizon_ridge: available default" in output
    assert "- sklearn:" not in output
