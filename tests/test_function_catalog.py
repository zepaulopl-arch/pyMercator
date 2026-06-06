from __future__ import annotations

from pathlib import Path

from pymercator.function_catalog import (
    catalog_functions,
    render_function_catalog,
    write_function_catalog,
)


def test_catalog_functions_detects_functions_classes_domains_and_roles(tmp_path: Path) -> None:
    module = tmp_path / "src" / "pymercator" / "feature_engine.py"
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text(
        """
class FeatureBuilder:
    def build_matrix(self, rows):
        return rows

def load_features(path):
    return []

def render_feature_summary(payload):
    return str(payload)

def _private_helper():
    return None
""",
        encoding="utf-8",
    )

    payload = catalog_functions(tmp_path)

    assert payload["status"] == "OK"
    assert payload["summary"]["functions_total"] == 4
    assert payload["summary"]["functions_public"] == 3
    assert payload["summary"]["functions_private"] == 1
    assert payload["summary"]["classes_total"] == 1
    assert payload["domains"]["features"] >= 1
    assert payload["roles"]["builder"] >= 1
    assert payload["roles"]["loader"] >= 1
    assert payload["roles"]["renderer"] >= 1


def test_render_function_catalog_contains_sections(tmp_path: Path) -> None:
    module = tmp_path / "src" / "pymercator" / "context_engine.py"
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text(
        """
def build_context():
    return {}

def render_context(payload):
    return ""
""",
        encoding="utf-8",
    )

    output = render_function_catalog(catalog_functions(tmp_path))

    assert "AURUM FUNCTION CATALOG" in output
    assert "SUMMARY" in output
    assert "DOMAINS" in output
    assert "ROLES" in output
    assert "TOP MODULES" in output


def test_write_function_catalog_writes_json(tmp_path: Path) -> None:
    module = tmp_path / "src" / "pymercator" / "short_execution.py"
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text("def evaluate_short_execution():\\n    return {}\\n", encoding="utf-8")

    payload = catalog_functions(tmp_path)
    output = write_function_catalog(payload, tmp_path / "out" / "catalog.json")

    assert output.exists()
    assert "aurum_function_catalog.v1" in output.read_text(encoding="utf-8")
