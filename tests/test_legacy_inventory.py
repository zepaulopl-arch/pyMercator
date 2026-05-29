import json
from pathlib import Path

from pymercator.legacy_inventory import (
    scan_legacy_project,
    write_legacy_inventory,
)


def test_scan_legacy_project_classifies_candidate_files(tmp_path: Path):
    legacy = tmp_path / "legacy"
    legacy.mkdir()

    (legacy / "features.py").write_text(
        "def build_features():\n    return []\n",
        encoding="utf-8",
    )
    (legacy / "model_ensemble.py").write_text(
        "from sklearn.ensemble import RandomForestClassifier\n",
        encoding="utf-8",
    )
    (legacy / "ibov_tickers.csv").write_text(
        "ticker\nPETR4.SA\nVALE3.SA\n",
        encoding="utf-8",
    )

    payload = scan_legacy_project(legacy)

    assert payload["file_count"] == 3
    assert payload["python_files"] == 2
    assert payload["data_files"] == 1
    assert payload["category_counts"]["features"] >= 1
    assert payload["category_counts"]["models"] >= 1
    assert payload["category_counts"]["assets"] >= 1


def test_write_legacy_inventory_creates_txt_and_json(tmp_path: Path):
    legacy = tmp_path / "legacy"
    output = tmp_path / "inventory"
    legacy.mkdir()

    (legacy / "news_fetcher.py").write_text(
        "import requests\n\ndef fetch_news():\n    return []\n",
        encoding="utf-8",
    )

    summary = write_legacy_inventory(
        legacy_path=legacy,
        output_dir=output,
    )

    txt_path = Path(summary["txt_path"])
    json_path = Path(summary["json_path"])

    assert txt_path.exists()
    assert json_path.exists()
    assert "PYMERCATOR LEGACY INVENTORY" in txt_path.read_text(encoding="utf-8")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["file_count"] == 1
    assert payload["category_counts"]["news"] >= 1
