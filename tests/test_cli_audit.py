from __future__ import annotations

from pathlib import Path

from pymercator.cli import main


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def test_cli_audit_system_runs_against_tmp_project(tmp_path: Path, capsys) -> None:
    for script in ("signal.ps1", "review.ps1", "train.ps1", "weekend.ps1"):
        _touch(tmp_path / "scripts" / script)
    _touch(tmp_path / "src" / "pymercator" / "__init__.py")
    _touch(tmp_path / "src" / "pymercator" / "feature_builder.py")
    _touch(tmp_path / "src" / "pymercator" / "model_training.py")
    _touch(tmp_path / "config" / "policy.json")

    exit_code = main(["audit", "system", "--root", str(tmp_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "AURUM SYSTEM AUDIT" in output
    assert "official_found" in output
    assert "feature_modules" in output
    assert "engine_modules" in output


def test_cli_audit_system_json_runs_against_tmp_project(tmp_path: Path, capsys) -> None:
    for script in ("signal.ps1", "review.ps1", "train.ps1", "weekend.ps1"):
        _touch(tmp_path / "scripts" / script)
    _touch(tmp_path / "src" / "pymercator" / "__init__.py")

    exit_code = main(["audit", "system", "--root", str(tmp_path), "--json"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"schema_version": "aurum_system_audit.v1"' in output
    assert '"official_scripts"' in output


def test_cli_audit_functions_runs_against_tmp_project(tmp_path: Path, capsys) -> None:
    module = tmp_path / "src" / "pymercator" / "feature_engine.py"
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text(
        "def build_feature_matrix():\n    return []\n",
        encoding="utf-8",
    )

    exit_code = main(["audit", "functions", "--root", str(tmp_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "AURUM FUNCTION CATALOG" in output
    assert "functions_total" in output
    assert "features" in output


def test_cli_audit_functions_json_and_output(tmp_path: Path, capsys) -> None:
    module = tmp_path / "src" / "pymercator" / "context_engine.py"
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text(
        "def build_context():\n    return {}\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "catalog.json"

    exit_code = main(
        [
            "audit",
            "functions",
            "--root",
            str(tmp_path),
            "--json",
            "--output",
            str(output_path),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert output_path.exists()
    assert '"schema_version": "aurum_function_catalog.v1"' in output
