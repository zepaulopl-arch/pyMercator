param([string]$PY = "")

$ErrorActionPreference = "Stop"
$env:NO_COLOR = "1"
$env:PY_COLORS = "0"
$env:CLICOLOR = "0"

. (Join-Path $PSScriptRoot "ops_common.ps1")

$scriptName = Split-Path -Leaf $PSCommandPath
$PY = Initialize-PyMercatorScript -RequestedPython $PY -ScriptName $scriptName
$logDir = New-PyMercatorLogDir -Prefix "daily_train" -ScriptName $scriptName
$listName = $script:PYMERCATOR_DEFAULT_LIST
$profiles = @("CON", "BAL", "AGR", "RLX")
$updateStatus = "storage\context\latest_update_status.json"

function New-ProfilePaths {
    param([string]$Profile)

    return @{
        Report = Join-Path $logDir "report_${Profile}.txt"
        Json = Join-Path $logDir "report_${Profile}.json"
        RunDir = Join-Path $logDir "run_${Profile}"
        Basket = Join-Path $logDir "basket_${Profile}.csv"
        Log = Join-Path $logDir "run_${Profile}.log"
    }
}

Write-PyMercatorRuntimeHeader -Title "PYMERCATOR DAILY TRAIN"

Invoke-PyMercatorStep `
    -Python $PY `
    -Name "Update $listName" `
    -PyArgs @("update", "--list", $listName) `
    -LogFile (Join-Path $logDir "00_update_ibov.log")

Invoke-PyMercatorStep `
    -Python $PY `
    -Name "Diag" `
    -PyArgs @("diag") `
    -LogFile (Join-Path $logDir "00_diag.log")

Invoke-PyMercatorStep `
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
    -LogFile (Join-Path $logDir "01_universe_diagnose.log")

Invoke-PyMercatorStep `
    -Python $PY `
    -Name "Train multi-horizon details" `
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
        "--details",
        "--output",
        "storage\prediction\latest_train_detail_report.txt"
    ) `
    -LogFile (Join-Path $logDir "02_train_details.log")

$conBasket = ""
foreach ($profile in $profiles) {
    $paths = New-ProfilePaths -Profile $profile
    if ($profile -eq "CON") {
        $conBasket = $paths.Basket
    }
    Invoke-PyMercatorStep `
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

Invoke-PyMercatorStep `
    -Python $PY `
    -Name "Basket show CON" `
    -PyArgs @("basket", "--profile", "CON", "show", "--output", $conBasket) `
    -LogFile (Join-Path $logDir "07_basket_show_CON.log") `
    -Critical $false

Write-RunManifest -Status "OK" -Outputs @{
    train_detail_report = "storage\prediction\latest_train_detail_report.txt"
    update_status = $updateStatus
    con_basket_csv = $conBasket
    con_basket_json = [System.IO.Path]::ChangeExtension($conBasket, ".json")
    runtime_dir = $logDir
}

Write-Host ""
Write-Host "============================================================"
Write-Host "DAILY TRAIN FINISHED"
Write-Host "RUNTIME: $logDir"
Write-Host "============================================================"
