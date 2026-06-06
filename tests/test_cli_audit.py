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
