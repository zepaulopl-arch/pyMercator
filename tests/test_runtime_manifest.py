import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _ps_quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def test_operational_scripts_use_ops_common_and_runtime_config():
    assert (ROOT / "config" / "runtime.json").exists()
    assert (ROOT / "scripts" / "ops_common.ps1").exists()
    runtime_config = json.loads(
        (ROOT / "config" / "runtime.json").read_text(encoding="utf-8-sig")
    )
    assert runtime_config["schema_version"] == "runtime_config.v1"

    for script_name in (
        "run_daily_signal.ps1",
        "run_daily_train.ps1",
        "run_weekend_full.ps1",
    ):
        text = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")
        assert "ops_common.ps1" in text
        assert "Initialize-PyMercatorScript" in text
        assert "Write-RunManifest" in text
        assert "[switch]$Color" in text
        assert "$null = Invoke-" in text
        assert "C:\\Users\\zepau\\anaconda3\\python.exe" not in text
        assert "--no-color" not in text
        if script_name == "run_daily_train.ps1":
            assert "Show-PyMercatorProfileSummary" in text

    ops_common = (ROOT / "scripts" / "ops_common.ps1").read_text(encoding="utf-8")
    assert "PROFILE SUMMARY" in ops_common
    assert "ConvertFrom-Json" in ops_common

    common = (ROOT / "scripts" / "ops_common.ps1").read_text(encoding="utf-8")
    assert "Get-PyMercatorColorArgs" in common
    assert 'return @("--no-color")' in common
    assert 'return @("--color", $script:PYMERCATOR_COLOR)' in common
    assert "Remove-AnsiFromFile" in common


def test_ops_common_creates_runtime_manifest():
    powershell = shutil.which("powershell")
    if not powershell:
        pytest.skip("PowerShell is not available")

    command = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            f". {_ps_quote(ROOT / 'scripts' / 'ops_common.ps1')}",
            (
                "$py = Initialize-PyMercatorScript "
                f"-RequestedPython {_ps_quote(sys.executable)} "
                "-ScriptName 'test_runtime.ps1'"
            ),
            "$dir = New-PyMercatorLogDir -Prefix 'pytest_manifest' -ScriptName 'test_runtime.ps1'",
            (
                "Run-Step -Name 'Python version' "
                "-Command @($py, '--version') "
                "-LogFile (Join-Path $dir 'python_version.log') | Out-Null"
            ),
            (
                "Write-RunManifest -Status 'OK' "
                "-Outputs @{ report_json = 'report.json'; update_status = 'latest_update_status.json' }"
            ),
            "Write-Output $script:PYMERCATOR_MANIFEST_PATH",
        ]
    )

    result = subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    manifest_path = Path([line for line in result.stdout.splitlines() if line.strip()][-1])
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        assert payload["schema_version"] == "runtime_manifest.v1"
        assert payload["script"] == "test_runtime.ps1"
        assert payload["python"]["executable"]
        assert payload["python"]["version"]
        assert payload["git"]["commit"]
        assert isinstance(payload["git"]["dirty"], bool)
        assert payload["commands"][0]["name"] == "Python version"
        assert payload["commands"][0]["status"] == "OK"
        assert payload["outputs"]["report_json"] == "report.json"
    finally:
        shutil.rmtree(manifest_path.parent, ignore_errors=True)
