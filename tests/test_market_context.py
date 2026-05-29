import json
from pathlib import Path

from pymercator.market_context import (
    load_market_context,
    validate_market_context,
    write_market_context_template,
)


def test_write_and_load_market_context_template(tmp_path: Path):
    output = tmp_path / "market_context.json"

    write_market_context_template(output)

    assert output.exists()

    context = load_market_context(output)
    validation = validate_market_context(output)

    assert context["headline_tags"] == []
    assert context["market_trend"] == "CHOPPY"
    assert context["market_volatility"] == "NORMAL"
    assert validation["valid"] is True


def test_load_market_context_normalizes_tags(tmp_path: Path):
    output = tmp_path / "market_context.json"

    output.write_text(
        json.dumps(
            {
                "headline_tags": "fed,copom,oil",
                "market_trend": "down",
                "market_volatility": "high",
                "notes": "stress test",
            }
        ),
        encoding="utf-8",
    )

    context = load_market_context(output)

    assert context["headline_tags"] == ["FED", "COPOM", "OIL"]
    assert context["market_trend"] == "DOWN"
    assert context["market_volatility"] == "HIGH"
