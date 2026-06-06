from __future__ import annotations

import json
from pathlib import Path

from pymercator.cli import main


def _write_local_sources(tmp_path: Path) -> dict[str, Path]:
    copom = tmp_path / "copom.csv"
    copom.write_text("date,event,source\n2099-06-17,COPOM,LOCAL\n", encoding="utf-8")
    commodities = tmp_path / "commodities.csv"
    commodities.write_text("name,value,change_pct,risk,source,updated_at\noil,82.1,1.4,HIGH,LOCAL,2026-06-06\n", encoding="utf-8")
    earnings = tmp_path / "earnings.csv"
    earnings.write_text("date,ticker,event,risk,source\n2099-06-10,PETR4,EARNINGS,MEDIUM,LOCAL\n", encoding="utf-8")
    geopolitical = tmp_path / "geo.json"
    geopolitical.write_text(json.dumps({"geopolitical_risk": "HIGH"}), encoding="utf-8")
    sector = tmp_path / "sector.json"
    sector.write_text(json.dumps({"energy": "WATCH"}), encoding="utf-8")
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


def test_context_update_show_explain_audit(tmp_path: Path, capsys) -> None:
    paths = _write_local_sources(tmp_path)
    output = tmp_path / "ctx.json"

    exit_code = main(
        [
            "context",
            "update",
            "--offline",
            "--output",
            str(output),
            "--existing-context",
            str(paths["existing"]),
            "--copom-csv",
            str(paths["copom"]),
            "--commodities-csv",
            str(paths["commodities"]),
            "--earnings-csv",
            str(paths["earnings"]),
            "--geopolitical-json",
            str(paths["geopolitical"]),
            "--sector-json",
            str(paths["sector"]),
        ]
    )
    assert exit_code == 0
    assert output.exists()
    assert "AURUM CONTEXT" in capsys.readouterr().out

    assert main(["context", "show", "--context", str(output)]) == 0
    assert "AURUM CONTEXT" in capsys.readouterr().out

    assert main(["context", "explain", "--context", str(output)]) == 0
    assert "AURUM CONTEXT EXPLAIN" in capsys.readouterr().out

    assert main(["context", "audit", "--context", str(output)]) == 0
    assert "AURUM CONTEXT AUDIT" in capsys.readouterr().out
