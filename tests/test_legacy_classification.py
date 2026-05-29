import json
from pathlib import Path

from pymercator.legacy_classification import (
    classify_legacy_inventory,
    write_legacy_classification,
)


def _write_inventory(path: Path) -> None:
    payload = {
        "root": "C:/legacy",
        "files": [
            {
                "path": "config/assets/ibov_assets.yaml",
                "extension": ".yaml",
                "size_bytes": 100,
                "categories": ["assets"],
                "content_hints": [],
            },
            {
                "path": "config/universes/ibov.yaml",
                "extension": ".yaml",
                "size_bytes": 100,
                "categories": ["indices"],
                "content_hints": [],
            },
            {
                "path": "app/features.py",
                "extension": ".py",
                "size_bytes": 100,
                "categories": ["features"],
                "content_hints": ["functions"],
            },
            {
                "path": "artifacts/models/PETR4_SA/train/model_d20.pkl",
                "extension": ".pkl",
                "size_bytes": 100,
                "categories": ["models"],
                "content_hints": [],
            },
            {
                "path": ".pytest_tmp_run/test/output.csv",
                "extension": ".csv",
                "size_bytes": 100,
                "categories": ["backtests"],
                "content_hints": [],
            },
        ],
    }

    path.write_text(json.dumps(payload), encoding="utf-8")


def test_classify_legacy_inventory_assigns_decisions(tmp_path: Path):
    inventory = tmp_path / "legacy_inventory.json"
    _write_inventory(inventory)

    payload = classify_legacy_inventory(inventory)

    assert payload["decision_counts"]["MIGRAR_AGORA"] == 3
    assert payload["decision_counts"]["MIGRAR_DEPOIS"] == 1
    assert payload["decision_counts"]["IGNORAR"] == 1


def test_write_legacy_classification_outputs_files(tmp_path: Path):
    inventory = tmp_path / "legacy_inventory.json"
    output = tmp_path / "out"
    _write_inventory(inventory)

    summary = write_legacy_classification(
        inventory_path=inventory,
        output_dir=output,
    )

    txt_path = Path(summary["txt_path"])
    json_path = Path(summary["json_path"])

    assert txt_path.exists()
    assert json_path.exists()
    assert "PYMERCATOR LEGACY CLASSIFICATION" in txt_path.read_text(
        encoding="utf-8"
    )
