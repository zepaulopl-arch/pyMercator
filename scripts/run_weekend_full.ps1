param(
    [string]$PY = "",
    [switch]$Color
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "ops_common.ps1")

$scriptName = Split-Path -Leaf $PSCommandPath
$PY = Initialize-PyMercatorScript -RequestedPython $PY -ScriptName $scriptName
Set-PyMercatorColorMode -Enabled ([bool]$Color)
$logDir = New-PyMercatorLogDir -Prefix "weekend_full" -ScriptName $scriptName
$listName = $script:PYMERCATOR_DEFAULT_LIST
$profiles = @("CON", "BAL", "AGR", "RLX")
$updateStatus = "storage\context\latest_update_status.json"
$trainLog = Join-Path $logDir "04_train_autotune_details.log"
$scenarioPositiveLog = Join-Path $logDir "09_scenario_positive.log"
$pytestLog = Join-Path $logDir "10_pytest.log"
$conPaths = $null

function New-ProfilePaths {
    param([string]$Profile)

    return Get-PyMercatorProfilePaths -LogDir $logDir -Profile $Profile
}

Write-PyMercatorRuntimeHeader -Title "PYMERCATOR WEEKEND FULL"

$null = Invoke-NativeStep `
    -Name "Install editable package" `
    -Command @($PY, "-m", "pip", "install", "-e", ".") `
    -LogFile (Join-Path $logDir "00_pip_install_editable.log")

$null = Invoke-PyMercatorStep `
    -Python $PY `
    -Name "Diag" `
    -PyArgs @("diag") `
    -LogFile (Join-Path $logDir "01_diag.log")

$null = Invoke-PyMercatorStep `
    -Python $PY `
    -Name "Update $listName" `
    -PyArgs @("update", "--list", $listName) `
    -LogFile (Join-Path $logDir "02_update_ibov.log")

$null = Invoke-PyMercatorStep `
    -Python $PY `
    -Name "Universe diagnose" `
    -PyArgs @(
        "universe",
        "diagnose",
        "--file",
        "data\universes\ibov_live.csv",
        "--policy",
        "config\policy.json"
    ) `
    -LogFile (Join-Path $logDir "03_universe_diagnose.log")

$null = Invoke-PyMercatorStep `
    -Python $PY `
    -Name "Train multi-horizon autotune details" `
    -PyArgs @(
        "train",
        "--horizons",
        "5,20,60",
        "--engines",
        "extratrees,randomforest,gradientboosting",
        "--meta",
        "ridge",
        "--observer",
        "weighted",
        "--weights",
        "D5=0.25,D20=0.35,D60=0.40",
        "--autotune",
        "--details",
        "--output",
        "storage\prediction\latest_train_detail_report.txt"
    ) `
    -LogFile $trainLog

foreach ($profile in $profiles) {
    $paths = New-ProfilePaths -Profile $profile
    if ($profile -eq "CON") {
        $conPaths = $paths
    }
    $null = Invoke-PyMercatorStep `
        -Python $PY `
        -Name "Run $profile basket" `
        -PyArgs @(
            "run",
            "--profile",
            $profile,
            "--basket",
            "--report-output",
            $paths.Report,
            "--json-output",
            $paths.Json,
            "--run-dir",
            $paths.RunDir,
            "--basket-output",
            $paths.Basket
        ) `
        -LogFile $paths.Log
}

$null = Invoke-PyMercatorStep `
    -Python $PY `
    -Name "Scenario positive AGR basket" `
    -PyArgs @(
        "scenario",
        "run",
        "--preset",
        "positive_risk_on",
        "--profile",
        "AGR",
        "--basket",
        "--report-output",
        (Join-Path $logDir "scenario_positive_report.txt"),
        "--json-output",
        (Join-Path $logDir "scenario_positive_report.json"),
        "--run-dir",
        (Join-Path $logDir "scenario_positive_run"),
        "--basket-output",
        (Join-Path $logDir "scenario_positive_basket.csv")
    ) `
    -LogFile $scenarioPositiveLog `
    -Critical $false

$null = Invoke-NativeStep `
    -Name "Pytest" `
    -Command @($PY, "-m", "pytest", "tests", "-q") `
    -LogFile $pytestLog `
    -Critical $false

$null = Write-RunManifest -Status "OK" -Outputs @{
    train_detail_report = "storage\prediction\latest_train_detail_report.txt"
    update_status = $updateStatus
    scenario_report_json = (Join-Path $logDir "scenario_positive_report.json")
    scenario_basket_csv = (Join-Path $logDir "scenario_positive_basket.csv")
    pytest_log = $pytestLog
    runtime_dir = $logDir
}

$scenarioExitCode = 0
$pytestExitCode = 0
foreach ($command in @($script:PYMERCATOR_MANIFEST.commands)) {
    if ($command.log -eq $scenarioPositiveLog) {
        $scenarioExitCode = [int]$command.exit_code
    }
    if ($command.log -eq $pytestLog) {
        $pytestExitCode = [int]$command.exit_code
    }
}

$null = Show-PyMercatorProfileSummary -LogDir $logDir -Profiles $profiles -SkipVerdict
$systemChecks = Show-PyMercatorSystemChecks `
    -ScenarioLog $scenarioPositiveLog `
    -ScenarioExitCode $scenarioExitCode `
    -PytestLog $pytestLog `
    -PytestExitCode $pytestExitCode
Show-PyMercatorVerdict
Show-PyMercatorKeyFiles -Files @{
    train_log = $trainLog
    pytest_log = $pytestLog
    report_CON = $conPaths.Report
    report_CON_json = $conPaths.Json
    basket_CON = $conPaths.Basket
    manifest = $script:PYMERCATOR_MANIFEST_PATH
}

if ($systemChecks.ScenarioPositive -eq "FAIL" -or $systemChecks.Pytest -eq "FAIL") {
    $null = Write-RunManifest -Status "FAIL"
    throw "WEEKEND FULL FAILED: system checks failed"
}

Write-Host ""
Write-Host "============================================================"
Write-Host "WEEKEND FULL FINISHED"
Write-Host "RUNTIME: $logDir"
Write-Host "============================================================"
