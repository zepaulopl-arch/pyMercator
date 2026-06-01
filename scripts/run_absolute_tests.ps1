param(
    [string]$Python = "",
    [switch]$SkipUpdate,
    [switch]$SkipTrain
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

if (-not $Python) {
    if ($env:PYMERCATOR_PYTHON) {
        $Python = $env:PYMERCATOR_PYTHON
    } else {
        $Python = "python"
    }
}

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$logDir = Join-Path "runtime" "absolute_tests_$ts"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$failures = New-Object System.Collections.Generic.List[string]

function Add-Failure {
    param([string]$Message)
    Write-Host "FAIL: $Message" -ForegroundColor Red
    $script:failures.Add($Message) | Out-Null
}

function Run-Native {
    param(
        [string]$Name,
        [string[]]$Command,
        [string]$LogFile,
        [bool]$Critical = $true
    )

    Write-Host ""
    Write-Host "============================================================"
    Write-Host "STEP: $Name"
    Write-Host "CMD : $($Command -join ' ')"
    Write-Host "LOG : $LogFile"
    Write-Host "============================================================"

    $exe = $Command[0]
    $exeArgs = @()
    if ($Command.Count -gt 1) {
        $exeArgs = $Command[1..($Command.Count - 1)]
    }

    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $exe @exeArgs 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $LogFile
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }

    if ($code -ne 0) {
        $msg = "$Name failed with exit code $code"
        Add-Failure $msg
        if ($Critical) {
            throw $msg
        }
    }
}

function Run-PyMercator {
    param(
        [string]$Name,
        [string[]]$PyArgs,
        [string]$LogFile,
        [bool]$Critical = $true
    )

    $command = @($Python, "-m", "pymercator") + $PyArgs
    Run-Native -Name $Name -Command $command -LogFile $LogFile -Critical $Critical
}

function Run-PythonBlock {
    param(
        [string]$Name,
        [string]$Code,
        [string]$LogFile,
        [bool]$Critical = $true
    )

    Write-Host ""
    Write-Host "============================================================"
    Write-Host "STEP: $Name"
    Write-Host "LOG : $LogFile"
    Write-Host "============================================================"

    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $Code | & $Python - 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $LogFile
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }

    if ($code -ne 0) {
        $msg = "$Name failed with exit code $code"
        Add-Failure $msg
        if ($Critical) {
            throw $msg
        }
    }
}

function Run-ExpectedPyMercatorFailure {
    param(
        [string]$Name,
        [string[]]$PyArgs,
        [string]$LogFile,
        [string]$ExpectedText
    )

    Write-Host ""
    Write-Host "============================================================"
    Write-Host "STEP: $Name"
    Write-Host "CMD : $Python -m pymercator $($PyArgs -join ' ')"
    Write-Host "LOG : $LogFile"
    Write-Host "============================================================"

    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Python -m pymercator @PyArgs 2>&1 |
            ForEach-Object { "$_" } |
            Tee-Object -FilePath $LogFile
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    $text = Get-Content -LiteralPath $LogFile -Raw

    if ($code -eq 0) {
        Add-Failure "$Name unexpectedly succeeded"
        return
    }
    if ($ExpectedText -and $text -notlike "*$ExpectedText*") {
        Add-Failure "$Name failed without expected text: $ExpectedText"
        return
    }

    Write-Host "PASS: $Name failed as expected with exit code $code" -ForegroundColor Green
}

Write-Host ""
Write-Host "============================================================"
Write-Host " PYMERCATOR ABSOLUTE TEST SUITE"
Write-Host " LOG DIR: $logDir"
Write-Host "============================================================"

Run-Native `
  -Name "Python version" `
  -Command @($Python, "--version") `
  -LogFile (Join-Path $logDir "00_python_version.txt")

Run-Native `
  -Name "Install editable" `
  -Command @($Python, "-m", "pip", "install", "-e", ".") `
  -LogFile (Join-Path $logDir "01_install_editable.txt")

Run-PyMercator `
  -Name "Diag before" `
  -PyArgs @("diag") `
  -LogFile (Join-Path $logDir "02_diag_before.txt")

Run-PythonBlock `
  -Name "Validate prediction config defaults" `
  -LogFile (Join-Path $logDir "03_validate_prediction_config.txt") `
  -Code @'
import json
from pathlib import Path

payload = json.loads(Path("config/prediction.json").read_text(encoding="utf-8"))
operational = payload.get("operational", {})
errors = []

if operational.get("default_engine") != "multi_horizon_ridge":
    errors.append("operational.default_engine must be multi_horizon_ridge")
if operational.get("per_horizon_engine") != "ridge_ensemble":
    errors.append("operational.per_horizon_engine must be ridge_ensemble")
if operational.get("horizons") != [5, 20, 60]:
    errors.append("operational horizons must be [5, 20, 60]")
if operational.get("base_engines") != ["extratrees", "randomforest", "gradientboosting"]:
    errors.append("operational base engines must be extratrees, randomforest, gradientboosting")

print(json.dumps(payload, indent=2, ensure_ascii=False))
if errors:
    print("\nFAILURES:")
    for error in errors:
        print("-", error)
    raise SystemExit(1)

print("\nPREDICTION CONFIG OK")
'@

if (-not $SkipUpdate) {
    Run-PyMercator `
      -Name "Update IBOV" `
      -PyArgs @("update", "--list", "IBOV") `
      -LogFile (Join-Path $logDir "04_update_ibov.txt")
}

Run-PyMercator `
  -Name "Diag after update" `
  -PyArgs @("diag") `
  -LogFile (Join-Path $logDir "05_diag_after_update.txt")

Run-PyMercator `
  -Name "Prices check" `
  -PyArgs @("prices", "check", "--prices-dir", "data\prices") `
  -LogFile (Join-Path $logDir "06_prices_check.txt")

if (-not $SkipTrain) {
    Run-PyMercator `
      -Name "Train operational" `
      -PyArgs @("train") `
      -LogFile (Join-Path $logDir "07_train_operational.txt")
}

Run-PythonBlock `
  -Name "Validate latest evaluation JSON" `
  -LogFile (Join-Path $logDir "08_validate_latest_evaluation_json.txt") `
  -Code @'
import json
from pathlib import Path

path = Path("storage/prediction/latest_evaluation.json")
if not path.exists():
    raise SystemExit("latest_evaluation.json not found")

payload = json.loads(path.read_text(encoding="utf-8"))
errors = []

if payload.get("engine_used") != "multi_horizon_ridge":
    errors.append("latest_evaluation engine_used must be multi_horizon_ridge")
if payload.get("horizons") != [5, 20, 60]:
    errors.append("latest_evaluation horizons must be [5, 20, 60]")
if payload.get("operational") is not True:
    errors.append("latest_evaluation operational must be true")
if payload.get("experimental") is not False:
    errors.append("latest_evaluation experimental must be false")
if "horizon" in payload:
    errors.append("latest_evaluation must not use single-horizon legacy key 'horizon'")
if payload.get("is_baseline") is not False:
    errors.append("latest_evaluation must not be baseline")
if not payload.get("model_quality"):
    errors.append("model_quality missing")
if "dropped_assets_by_horizon" not in payload:
    errors.append("dropped_assets_by_horizon missing")

for horizon in ("d5", "d20", "d60"):
    if not Path(f"storage/prediction/{horizon}/latest_evaluation.json").exists():
        errors.append(f"missing per-horizon evaluation for {horizon}")

print(json.dumps(payload, indent=2, ensure_ascii=False))
if errors:
    print("\nFAILURES:")
    for error in errors:
        print("-", error)
    raise SystemExit(1)

print("\nLATEST EVALUATION JSON OK")
'@

foreach ($profile in @("CON", "BAL", "AGR", "RLX")) {
    Run-PyMercator `
      -Name "Run $profile basket" `
      -PyArgs @("run", "--profile", $profile, "--basket") `
      -LogFile (Join-Path $logDir "09_run_${profile}_basket.txt")
}

Run-PythonBlock `
  -Name "Validate daily report JSON" `
  -LogFile (Join-Path $logDir "10_validate_daily_report_json.txt") `
  -Code @'
import json
from pathlib import Path

path = Path("storage/reports/latest_daily_report.json")
payload = json.loads(path.read_text(encoding="utf-8"))
prediction = payload.get("prediction", {})
errors = []

if prediction.get("engine") != "multi_horizon_ridge":
    errors.append("report prediction.engine must be multi_horizon_ridge")
if prediction.get("horizons") != [5, 20, 60]:
    errors.append("report prediction.horizons must be [5, 20, 60]")
if not prediction.get("model_quality"):
    errors.append("report prediction.model_quality missing")

for index, decision in enumerate(payload.get("decisions", []), start=1):
    item = decision.get("prediction", {})
    for key in ("d5_score", "d20_score", "d60_score", "combined_score", "dominant_horizon", "behavior"):
        if key not in item:
            errors.append(f"decision {index} prediction missing {key}")
            break

print(json.dumps(payload, indent=2, ensure_ascii=False))
if errors:
    print("\nFAILURES:")
    for error in errors:
        print("-", error)
    raise SystemExit(1)

print("\nDAILY REPORT JSON OK")
'@

$beforeHash = ""
if (Test-Path -LiteralPath "storage/prediction/latest_evaluation.json") {
    $beforeHash = (Get-FileHash -Algorithm SHA256 -LiteralPath "storage/prediction/latest_evaluation.json").Hash
}

Run-ExpectedPyMercatorFailure `
  -Name "Experimental old horizons should not pass as operational" `
  -PyArgs @(
      "train",
      "--horizons", "5,10,20",
      "--engines", "extratrees,randomforest",
      "--weights", "D5=0.2,D10=0.3,D20=0.5"
  ) `
  -LogFile (Join-Path $logDir "11_experimental_old_horizons.txt") `
  -ExpectedText "Non-standard horizons require --experimental"

if ($beforeHash) {
    $afterHash = (Get-FileHash -Algorithm SHA256 -LiteralPath "storage/prediction/latest_evaluation.json").Hash
    if ($beforeHash -ne $afterHash) {
        Add-Failure "old horizons rejection overwrote latest_evaluation.json"
    }
}

Run-Native `
  -Name "Pytest all" `
  -Command @($Python, "-m", "pytest", "-q", "--basetemp", "runtime\pytest_tmp") `
  -LogFile (Join-Path $logDir "12_pytest_all.txt")

Write-Host ""
Write-Host "============================================================"
Write-Host " FINAL SUMMARY"
Write-Host " LOG DIR: $logDir"
Write-Host " FAILURES: $($failures.Count)"
Write-Host "============================================================"

if ($failures.Count -gt 0) {
    $failures | Out-File (Join-Path $logDir "_FAILURES.txt") -Encoding utf8
    Write-Host ""
    Write-Host "TEST SUITE FINISHED WITH FAILURES" -ForegroundColor Red
    Write-Host "See: $(Join-Path $logDir '_FAILURES.txt')"
    throw "PYMERCATOR ABSOLUTE TEST FAILED WITH $($failures.Count) FAILURE(S)"
}

Write-Host ""
Write-Host "ALL ABSOLUTE TESTS PASSED" -ForegroundColor Green
Write-Host "Logs saved at: $logDir"
