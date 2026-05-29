from pymercator.market_context import (
    list_market_context_presets,
    load_market_context_preset,
)


def test_list_market_context_presets_contains_operational_presets():
    presets = list_market_context_presets()

    assert "normal" in presets
    assert "oil_war" in presets
    assert "fed_day" in presets
    assert "copom_day" in presets


def test_load_market_context_preset_normalizes_values():
    context = load_market_context_preset("oil_war")

    assert context["headline_tags"] == ["IRAN", "OIL", "WAR"]
    assert context["market_trend"] == "CHOPPY"
    assert context["market_volatility"] == "NORMAL"
    assert context["notes"]
