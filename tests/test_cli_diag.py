from pymercator.cli import main


def test_cli_diag_shows_operational_prediction_stack(monkeypatch, capsys):
    import pymercator.legacy_prediction_engines as engines_mod

    monkeypatch.setattr(engines_mod, "SKLEARN_AVAILABLE", True)
    monkeypatch.setattr(engines_mod, "XGBOOST_AVAILABLE", False)
    monkeypatch.setattr(engines_mod, "CATBOOST_AVAILABLE", False)

    exit_code = main(["diag"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "PYMERCATOR DIAG" in output
    assert "PREDICTION STACK:" in output
    assert "- status: OK" in output
    assert "- config: config/prediction.json" in output
    assert "- backend: sklearn" in output
    assert "- engine: multi_horizon_ridge" in output
    assert "- horizons: D5,D20,D60" in output
    assert "- weights: D5=0.25 D20=0.35 D60=0.40" in output
    assert "- base_models: extratrees,randomforest,gradientboosting" in output
    assert "- combiner: ridge" in output
    assert "- per_horizon_combiner: ridge_ensemble" in output
    assert "- observer: weighted" in output
    assert "- baseline_used: false" in output
    assert "OPTIONAL BACKENDS:" not in output
    assert "optional" not in output.lower()
    assert "xgboost" not in output.lower()
    assert "catboost" not in output.lower()
    assert "rolling_majority" not in output
    assert "LIBRARIES:" not in output
    assert "TECHNICAL PREDICTION ENGINES:" not in output
    assert "- sklearn available:" not in output
    assert "- sklearn:" not in output


def test_cli_diag_verbose_shows_technical_libraries_and_engines(monkeypatch, capsys):
    import pymercator.legacy_prediction_engines as engines_mod

    monkeypatch.setattr(engines_mod, "SKLEARN_AVAILABLE", True)
    monkeypatch.setattr(engines_mod, "XGBOOST_AVAILABLE", False)
    monkeypatch.setattr(engines_mod, "CATBOOST_AVAILABLE", False)

    exit_code = main(["diag", "--verbose"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "PREDICTION STACK:" in output
    assert "TECHNICAL CONFIG:" in output
    assert "- mode: operational" in output
    assert "- per_horizon_engine: ridge_ensemble" in output
    assert "- horizons: 5,20,60" in output
    assert "- base_engines: extratrees,randomforest,gradientboosting" in output
    assert "- meta_model: ridge" in output
    assert "- observer: weighted" in output
    assert "- weights: D5=0.25 D20=0.35 D60=0.40" in output
    assert "- min_assets: 30" in output
    assert "LIBRARIES:" in output
    assert "- sklearn available: True" in output
    assert "TECHNICAL PREDICTION ENGINES:" in output
    assert "- rolling_majority: available baseline" in output
    assert "- extratrees: available" in output
    assert "- randomforest: available" in output
    assert "- gradientboosting: available" in output
    assert "- ridge: available" in output
    assert "- ridge_ensemble: available per-horizon" in output
    assert "- multi_horizon_ridge: available default" in output
    assert "- sklearn:" not in output
