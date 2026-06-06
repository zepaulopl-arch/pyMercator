from __future__ import annotations

from pathlib import Path

from pymercator.audit_system import (
    audit_system,
    render_system_audit,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def test_audit_system_detects_official_and_legacy_scripts(tmp_path: Path) -> None:
    for script in ("signal.ps1", "review.ps1", "train.ps1", "weekend.ps1"):
        _touch(tmp_path / "scripts" / script)
    _touch(tmp_path / "scripts" / "run_daily_signal.ps1")
    _touch(tmp_path / "src" / "pymercator" / "__init__.py")
    _touch(tmp_path / "src" / "pymercator" / "feature_builder.py")
    _touch(tmp_path / "src" / "pymercator" / "model_training.py")
    _touch(tmp_path / "src" / "pymercator" / "market_context.py")
    _touch(tmp_path / "src" / "pymercator" / "short_execution.py")
    _touch(tmp_path / "config" / "policy.json")

    payload = audit_system(tmp_path)

    assert payload["official_scripts"]["count"] == 4
    assert payload["legacy_scripts"]["count"] == 1
    assert payload["legacy_scripts"]["found"] == ["scripts/run_daily_signal.ps1"]
    assert payload["status"] == "LEGACY_FOUND"
    assert payload["modules"]["feature_modules"]
    assert payload["modules"]["engine_modules"]
    assert payload["modules"]["context_modules"]
    assert payload["modules"]["short_modules"]
    assert payload["config_files"]["count"] == 1


def test_audit_system_ok_when_no_legacy_and_all_official_exist(tmp_path: Path) -> None:
    for script in ("signal.ps1", "review.ps1", "train.ps1", "weekend.ps1"):
        _touch(tmp_path / "scripts" / script)
    _touch(tmp_path / "src" / "pymercator" / "__init__.py")

    payload = audit_system(tmp_path)

    assert payload["status"] == "OK"
    assert payload["official_scripts"]["missing"] == []
    assert payload["legacy_scripts"]["found"] == []


def test_audit_system_reports_missing_official_script(tmp_path: Path) -> None:
    _touch(tmp_path / "scripts" / "signal.ps1")
    _touch(tmp_path / "src" / "pymercator" / "__init__.py")

    payload = audit_system(tmp_path)

    assert payload["status"] == "MISSING_OFFICIAL_SCRIPT"
    assert "scripts/review.ps1" in payload["official_scripts"]["missing"]


def test_render_system_audit_contains_key_sections(tmp_path: Path) -> None:
    for script in ("signal.ps1", "review.ps1", "train.ps1", "weekend.ps1"):
        _touch(tmp_path / "scripts" / script)
    _touch(tmp_path / "src" / "pymercator" / "__init__.py")
    _touch(tmp_path / "src" / "pymercator" / "features.py")
    _touch(tmp_path / "src" / "pymercator" / "prediction_engine.py")

    output = render_system_audit(audit_system(tmp_path))

    assert "AURUM SYSTEM AUDIT" in output
    assert "COMMANDS" in output
    assert "SCRIPTS" in output
    assert "MODULES" in output
    assert "feature_modules" in output
    assert "engine_modules" in output
