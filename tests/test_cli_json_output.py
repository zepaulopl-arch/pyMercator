import json
from pathlib import Path

from pymercator.cli import main


def test_daily_cli_writes_json_output_file(tmp_path: Path):
    output = tmp_path / "report.json"

    exit_code = main(
        [
            "daily",
            "--universe",
            "data/universes/ibov_sample.csv",
            "--headline-risk",
            "ACTIVE",
            "--headline-tags",
            "IRAN,OIL",
            "--profile",
            "AGR",
            "--json-output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert output.exists()

    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["universe_name"] == "IBOV"
    assert payload["profile"] == "AGR"
    assert payload["market_regime"]["headline_risk"] == "ACTIVE"
    assert "decisions" in payload
    assert len(payload["decisions"]) > 0
