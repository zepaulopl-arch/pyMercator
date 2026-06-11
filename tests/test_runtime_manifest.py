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

    expected_functions = {
        "daily_signal.ps1": "from aurum.core import run_daily",
        "daily_review.ps1": "from aurum.core import run_review",
        "weekly_train.ps1": "from aurum.core import run_weekly",
    }
    for script_name, function_import in expected_functions.items():
        text = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")
        assert "ops_common.ps1" in text
        assert "Initialize-AurumScript" in text
        assert "Write-RunManifest" in text
        assert "[switch]$Color" in text
        assert function_import in text
        assert "python -m aurum" not in text
        assert "-m aurum" not in text
        assert "-c $code" not in text
        assert "Set-Content -LiteralPath $tempPy" in text
        assert "C:\\Users\\zepau\\anaconda3\\python.exe" not in text
        assert "--no-color" not in text

    ops_common = (ROOT / "scripts" / "ops_common.ps1").read_text(encoding="utf-8")
    assert "PROFILE SUMMARY" in ops_common
    assert "ConvertFrom-Json" in ops_common

    common = (ROOT / "scripts" / "ops_common.ps1").read_text(encoding="utf-8")
    assert "Get-AurumColorArgs" in common
    assert 'return @("--no-color")' in common
    assert 'return @("--color", $script:AURUM_COLOR)' in common
    assert "Remove-AnsiFromFile" in common
    assert "Show-AurumSignals" in common
    assert "AURUM SIGNALS" in common

    daily_signal = (ROOT / "scripts" / "daily_signal.ps1").read_text(encoding="utf-8")
    assert "run_daily(**args)" in daily_signal

    daily_review = (ROOT / "scripts" / "daily_review.ps1").read_text(encoding="utf-8")
    assert "except FileNotFoundError" in daily_review
    assert "AURUM REVIEW | SNAPSHOT NOT FOUND" in daily_review
    assert "Se for revisar o sinal gerado hoje" in daily_review


def test_ops_common_creates_runtime_manifest():
    powershell = shutil.which("powershell")
    if not powershell:
        pytest.skip("PowerShell is not available")

    command = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            f". {_ps_quote(ROOT / 'scripts' / 'ops_common.ps1')}",
            (
                "$py = Initialize-AurumScript "
                f"-RequestedPython {_ps_quote(sys.executable)} "
                "-ScriptName 'test_runtime.ps1'"
            ),
            "$dir = New-AurumLogDir -Prefix 'pytest_manifest' -ScriptName 'test_runtime.ps1'",
            (
                "$code = Run-Step -Name 'Python version' "
                "-Command @($py, '-c', 'print(123)') "
                "-LogFile (Join-Path $dir 'python_version.log')"
            ),
            "if ($code -is [array]) { throw 'Run-Step returned array output' }",
            "if ([int]$code -ne 0) { throw \"Run-Step failed with code $code\" }",
            (
                "Write-RunManifest -Status 'OK' "
                "-Outputs @{ report_json = 'report.json'; update_status = 'latest_update_status.json' }"
            ),
            "Write-Output $script:AURUM_MANIFEST_PATH",
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


def test_ops_common_renders_daily_signal_screen(tmp_path: Path):
    powershell = shutil.which("powershell")
    if not powershell:
        pytest.skip("PowerShell is not available")

    report = tmp_path / "report_CON.json"
    basket = tmp_path / "basket_CON.csv"
    update = tmp_path / "latest_update_status.json"
    run_log = tmp_path / "02_run_CON_basket.log"
    observe_log = tmp_path / "03_observe_ibov.log"
    basket.write_text("ticker,status\n", encoding="utf-8")
    run_log.write_text("run log\n", encoding="utf-8")
    observe_log.write_text("observe log\n", encoding="utf-8")
    update.write_text(
        json.dumps(
            {
                "status": "OK",
                "freshness": {
                    "freshness_status": "WARNING",
                    "data_quality_score": 77.0,
                },
            }
        ),
        encoding="utf-8",
    )
    report.write_text(
        json.dumps(
            {
                "profile": "CON",
                "market_regime": {"regime": "RISK_OFF"},
                "market_context": {
                    "regime_summary": {
                        "market_regime": "RISK_OFF",
                        "market_trend": "DOWN",
                        "context_score": 47.6,
                    }
                },
                "prediction": {
                    "behavior": "AVOID",
                    "model_quality": {"status": "WEAK", "edge": -0.01},
                },
                "model_quality": "WEAK",
                "decision": {"actionable": 0, "watch": 1, "blocked": 2},
                "basket": {"status": "BLOCKED", "assets": 0, "reason": "no actionable"},
                "defensive_book": {"defensive_mode": "active"},
                "decisions": [
                    {
                        "asset": {"ticker": "AAA3"},
                        "ranking": {"context_score": 70.5},
                        "permission": {"status": "BLOCKED"},
                        "decision_label": "MODEL_WEAK",
                    }
                ],
                "short_candidates": [
                    {
                        "ticker": "BBB3",
                        "bias": "SHORT",
                        "score": 92.9,
                        "class": "SHORT_SETUP",
                        "short_setup_status": "SHORT_SETUP",
                        "borrow_status": "BORROW_DATA_MISSING",
                        "short_permission": "SHORT_BLOCKED",
                        "executable": False,
                        "reason": "weak trend/mom + risk-off",
                    }
                ],
                "short_observation_candidates": [
                    {
                        "ticker": "BBB3",
                        "bias": "SHORT",
                        "score": 92.9,
                        "class": "SHORT_SETUP",
                        "reason": "weak trend/mom + risk-off",
                        "executable": False,
                        "borrow_status": "BORROW_DATA_MISSING",
                        "permission": "SHORT_BLOCKED",
                    }
                ],
                "hedge_candidates": [
                    {
                        "target": "INDEX",
                        "action": "HEDGE_WATCH",
                        "reason": "risk-off + downtrend",
                    }
                ],
                "observation_candidates": [
                    {
                        "ticker": "AAA3",
                        "bias": "LONG",
                        "score": 75.0,
                        "obs_index": 75.0,
                        "class": "OBS_READY",
                        "reason": "strong trend/mom",
                        "executable": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    command = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            f". {_ps_quote(ROOT / 'scripts' / 'ops_common.ps1')}",
            "Set-AurumColorMode -Enabled $false",
            (
                "Show-AurumSignals "
                f"-ReportJson {_ps_quote(report)} "
                f"-BasketFile {_ps_quote(basket)} "
                f"-UpdateStatusFile {_ps_quote(update)} "
                f"-RunLog {_ps_quote(run_log)} "
                f"-ObserveLog {_ps_quote(observe_log)}"
            ),
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
    output = result.stdout
    assert "AURUM SIGNALS" in output
    assert "context_score" in output
    assert "47.6" in output
    assert "data_freshness" in output
    assert "WARNING" in output
    assert "data_quality" in output
    assert "77.0" in output
    assert "0 EXEC_READY | 1 DATA_BLOCKED" in output
    assert "LONG / BUY BOARD" in output
    assert "SHORT / SELL BOARD" in output
    assert "OBS_CLASS" in output
    assert "SIGNAL" in output
    assert "EXECUTION" in output
    assert "MAIN_REASON" in output
    assert "BUY_SETUP" in output
    assert "SELL_SETUP" in output
    assert "DATA_BLOCKED" in output
    assert "borrow data missing" in output
    assert "BUY / LONG SIGNALS" not in output
    assert "SELL-SHORT SIGNALS" not in output
    assert "SETUP_SCORE" not in output
    assert "PERMISSION" not in output
    assert "BLOCKED/DATA" not in output
    assert "HEDGE / DEFENSE" in output
    assert "INDEX" in output
    assert "risk-off + downtrend" in output
    assert "CASH" in output
    assert "PREFERRED" in output
    assert "LONG OBSERVATION" in output
    assert "SHORT OBSERVATION" in output
    assert "\nOBSERVATION\n" not in output
    assert "BASKET" in output
    assert "FINAL DECISION" in output
    assert "NO LONG TRADE." in output
    assert "OBS_READY" not in output
    assert "OBS_FAVORABLE" in output
    assert "\x1b[" not in output
    assert "\n0\n" not in output

    color_command = command.replace(
        "Set-AurumColorMode -Enabled $false",
        "Set-AurumColorMode -Enabled $true",
    )
    color_result = subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", color_command],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert color_result.returncode == 0, color_result.stderr + color_result.stdout
    assert "\x1b[" in color_result.stdout
    assert "\x1b[" not in report.read_text(encoding="utf-8")
    assert "\x1b[" not in basket.read_text(encoding="utf-8")
    assert "\x1b[" not in run_log.read_text(encoding="utf-8")
    assert "\x1b[" not in observe_log.read_text(encoding="utf-8")
