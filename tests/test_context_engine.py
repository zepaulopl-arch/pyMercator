from __future__ import annotations

import json
from pathlib import Path

from pymercator.context_engine.builder import build_market_context
from pymercator.context_engine.renderer import (
    render_context_audit,
    render_context_explain,
    render_context_show,
)


def _write_local_sources(tmp_path: Path) -> dict[str, Path]:
    copom = tmp_path / "copom.csv"
    copom.write_text("date,event,source\n2099-06-17,COPOM,LOCAL\n", encoding="utf-8")

    commodities = tmp_path / "commodities.csv"
    commodities.write_text(
        "name,value,change_pct,risk,source,updated_at\n"
        "oil,82.1,1.4,HIGH,LOCAL,2026-06-06\n"
        "iron_ore,105,-0.5,MEDIUM,LOCAL,2026-06-06\n",
        encoding="utf-8",
    )

    earnings = tmp_path / "earnings.csv"
    earnings.write_text("date,ticker,event,risk,source\n2099-06-10,PETR4,EARNINGS,MEDIUM,LOCAL\n", encoding="utf-8")

    geopolitical = tmp_path / "geo.json"
    geopolitical.write_text(json.dumps({"geopolitical_risk": "HIGH", "oil_war_risk": "HIGH"}), encoding="utf-8")

    sector = tmp_path / "sector.json"
    sector.write_text(json.dumps({"energy": {"bias": "WATCH"}}), encoding="utf-8")

    existing = tmp_path / "existing.json"
    existing.write_text(json.dumps({"market_trend": "DOWN", "market_volatility": "NORMAL"}), encoding="utf-8")

    return {
        "copom": copom,
        "commodities": commodities,
        "earnings": earnings,
        "geopolitical": geopolitical,
        "sector": sector,
        "existing": existing,
    }


def test_build_market_context_offline_with_local_sources(tmp_path: Path) -> None:
    paths = _write_local_sources(tmp_path)
    output = tmp_path / "latest_market_context.json"

    payload = build_market_context(
        output=output,
        existing_context_path=paths["existing"],
        use_network=False,
        copom_csv=paths["copom"],
        commodities_csv=paths["commodities"],
        earnings_csv=paths["earnings"],
        geopolitical_json=paths["geopolitical"],
        sector_json=paths["sector"],
    )

    assert output.exists()
    assert payload["schema_version"] == "market_context.v2"
    assert payload["market_trend"] == "DOWN"
    assert payload["commodities"]["oil_risk"] == "HIGH"
    assert payload["geopolitical"]["risk"] == "HIGH"
    assert payload["source_status"]["bcb_sgs"] == "SKIPPED"
    assert payload["source_status"]["commodities"] == "OK"


def test_context_renderers(tmp_path: Path) -> None:
    paths = _write_local_sources(tmp_path)
    payload = build_market_context(
        output=tmp_path / "ctx.json",
        existing_context_path=paths["existing"],
        use_network=False,
        copom_csv=paths["copom"],
        commodities_csv=paths["commodities"],
        earnings_csv=paths["earnings"],
        geopolitical_json=paths["geopolitical"],
        sector_json=paths["sector"],
    )

    assert "AURUM CONTEXT" in render_context_show(payload)
    assert "AURUM CONTEXT AUDIT" in render_context_audit(payload)
    assert "AURUM CONTEXT EXPLAIN" in render_context_explain(payload)
