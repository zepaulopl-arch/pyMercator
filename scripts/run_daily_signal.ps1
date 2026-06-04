param([string]$PY = "")

$ErrorActionPreference = "Stop"
$env:NO_COLOR = "1"
$env:PY_COLORS = "0"
$env:CLICOLOR = "0"

. (Join-Path $PSScriptRoot "ops_common.ps1")

$scriptName = Split-Path -Leaf $PSCommandPath
$PY = Initialize-PyMercatorScript -RequestedPython $PY -ScriptName $scriptName
$logDir = New-PyMercatorLogDir -Prefix "daily_signal" -ScriptName $scriptName
$listName = $script:PYMERCATOR_DEFAULT_LIST
$reportOutput = Join-Path $logDir "report_CON.txt"
$jsonOutput = Join-Path $logDir "report_CON.json"
$runDir = Join-Path $logDir "run_CON"
$basketOutput = Join-Path $logDir "basket_CON.csv"
$basketJson = [System.IO.Path]::ChangeExtension($basketOutput, ".json")
$updateStatus = "storage\context\latest_update_status.json"

Write-PyMercatorRuntimeHeader -Title "PYMERCATOR DAILY SIGNAL"

Invoke-PyMercatorStep `
    -Python $PY `
    -Name "Update $listName" `
    -PyArgs @("update", "--list", $listName) `
    -LogFile (Join-Path $logDir "00_update_ibov.log")

Invoke-PyMercatorStep `
    -Python $PY `
    -Name "Diag" `
    -PyArgs @("diag") `
    -LogFile (Join-Path $logDir "01_diag.log")

Invoke-PyMercatorStep `
    -Python $PY `
    -Name "Run CON basket" `
    -PyArgs @(
        "run",
        "--profile",
        "CON",
        "--basket",
        "--report-output",
        $reportOutput,
        "--json-output",
        $jsonOutput,
        "--run-dir",
        $runDir,
        "--basket-output",
        $basketOutput
    ) `
    -LogFile (Join-Path $logDir "02_run_CON_basket.log")

Invoke-PyMercatorStep `
    -Python $PY `
    -Name "Observe $listName" `
    -PyArgs @("observe", "--list", $listName) `
    -LogFile (Join-Path $logDir "03_observe_ibov.log") `
    -Critical $false

Invoke-PyMercatorStep `
    -Python $PY `
    -Name "Basket show" `
    -PyArgs @("basket", "show", "--output", $basketOutput) `
    -LogFile (Join-Path $logDir "04_basket_show.log") `
    -Critical $false

Write-RunManifest -Status "OK" -Outputs @{
    report_txt = $reportOutput
    report_json = $jsonOutput
    run_dir = $runDir
    basket_csv = $basketOutput
    basket_json = $basketJson
    update_status = $updateStatus
}

Write-Host ""
Write-Host "============================================================"
Write-Host "DAILY SIGNAL FINISHED"
Write-Host "RUNTIME: $logDir"
Write-Host "============================================================"
