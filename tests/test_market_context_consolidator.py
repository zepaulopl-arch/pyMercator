import json
from pathlib import Path

from pymercator.market_context import load_market_context
from pymercator.market_context_consolidator import (
    build_market_context,
    load_market_context_thresholds,
    write_market_context,
)


def _auto_context() -> dict:
    return {
        "headline_tags": ["RISK_OFF"],
        "market_trend": "DOWN",
        "market_volatility": "HIGH",
        "notes": "auto context",
        "metrics": {
            "ibov_volatility_20d_annualized_pct": 32.0,
            "brent_return_20d_pct": 12.0,
            "usdbrl_return_20d_pct": 7.0,
        },
    }


def test_market_context_auto_is_used_in_consolidation() -> None:
    payload = build_market_context(auto_context=_auto_context())

    assert payload["schema_version"] == "market_context.v2"
    assert payload["regime_summary"]["market_trend"] == "DOWN"
    assert payload["equity_indices"]["ibov"]["volatility"] == "HIGH"
    assert payload["context_sources"]["auto"] == "OK"
    assert "source_diagnostics" in payload
    assert payload["context_sources"]["bcb"] != "UNKNOWN"


def test_market_context_thresholds_are_loaded(tmp_path: Path) -> None:
    thresholds = tmp_path / "thresholds.json"
    thresholds.write_text(
        json.dumps(
            {
                "schema_version": "market_context_thresholds.v1",
                "weights": {"market_trend": 1.0},
                "sector_drivers": {"financials": ["rates"]},
            }
        ),
        encoding="utf-8",
    )

    payload = load_market_context_thresholds(thresholds)

    assert payload["schema_version"] == "market_context_thresholds.v1"
    assert payload["weights"]["market_trend"] == 1.0
    assert payload["sector_drivers"]["financials"] == ["rates"]


def test_manual_overrides_from_legacy_context_are_preserved(tmp_path: Path) -> None:
    legacy = {
        "headline_tags": ["IRAN", "OIL"],
        "market_trend": "CHOPPY",
        "market_volatility": "NORMAL",
        "notes": "manual stress",
        "geopolitical_risk": "HIGH",
    }

    payload = build_market_context(
        auto_context=_auto_context(),
        previous_context=legacy,
    )

    assert "IRAN" in payload["manual_overrides"]["headline_tags"]
    assert payload["manual_overrides"]["notes"] == "manual stress"
    assert payload["events"]["geopolitical_risk"] == "HIGH"


def test_market_context_schema_contains_required_sections() -> None:
    payload = build_market_context(auto_context=_auto_context())

    for field in (
        "macro",
        "fx",
        "commodities",
        "equity_indices",
        "sector_context",
        "corporate_calendar",
        "events",
        "regime_summary",
    ):
        assert field in payload


def test_write_market_context_consolidates_layers(tmp_path: Path) -> None:
    output = tmp_path / "latest_market_context.json"
    manual = tmp_path / "manual_context.json"
    thresholds = tmp_path / "thresholds.json"
    manual.write_text(
        json.dumps({"headline_tags": ["COPOM"], "notes": "manual note"}),
        encoding="utf-8",
    )
    thresholds.write_text(
        json.dumps({"schema_version": "market_context_thresholds.v1"}),
        encoding="utf-8",
    )

    payload = write_market_context(
        auto_context=_auto_context(),
        output=output,
        thresholds_path=thresholds,
        manual_context_path=manual,
    )
    loaded = json.loads(output.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "market_context.v2"
    assert loaded["schema_version"] == "market_context.v2"
    assert "COPOM" in loaded["headline_tags"]
    assert "source_diagnostics" in loaded


def test_legacy_market_context_is_upgraded_when_loaded(tmp_path: Path) -> None:
    output = tmp_path / "legacy_context.json"
    output.write_text(
        json.dumps(
            {
                "headline_tags": ["FED"],
                "market_trend": "down",
                "market_volatility": "high",
                "notes": "legacy",
            }
        ),
        encoding="utf-8",
    )

    context = load_market_context(output)

    assert context["schema_version"] == "market_context.v2"
    assert context["market_trend"] == "DOWN"
    assert context["headline_tags"] == ["FED"]
