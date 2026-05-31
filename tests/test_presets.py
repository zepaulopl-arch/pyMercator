from pymercator import presets


def test_load_defaults_when_missing(tmp_path):
    p = tmp_path / "no-file.json"
    cfg = presets.load_presets(str(p))
    assert isinstance(cfg, dict)
    assert cfg.get("default_profile") == "daily"


def test_resolve_profile_daily():
    cfg = presets.resolve_profile(None)
    assert cfg.get("profile") == "daily"
    assert "paths" in cfg


def test_get_prediction_defaults():
    pred = presets.get_prediction_defaults()
    assert pred.get("horizon") == 5
    assert isinstance(pred.get("engines"), list)
