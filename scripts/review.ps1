param(
    [string]$PY = "",
    [string]$RunDir = "",
    [double]$Capital = 10000.0,
    [ValidateSet("observation", "all")]
    [string]$Mode = "observation",
    [string]$Profile = "CON",
    [string]$PricesDir = "data/prices",
    [switch]$Color,
    [switch]$SkipUpdate
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "ops_common.ps1")

$scriptName = Split-Path -Leaf $PSCommandPath
$PY = Initialize-PyMercatorScript -RequestedPython $PY -ScriptName $scriptName
Set-PyMercatorColorMode -Enabled ([bool]$Color)

if (-not $RunDir) {
    $latestRun = Get-ChildItem -LiteralPath "runtime" -Directory -Filter "daily_signal_*" -ErrorAction SilentlyContinue |
    Sort-Object -Property LastWriteTime -Descending |
    Select-Object -First 1
    if ($null -eq $latestRun) {
        throw "No daily_signal runtime found. Run scripts/signal.ps1 first or pass -RunDir."
    }
    $RunDir = $latestRun.FullName
}

$RunDir = [System.IO.Path]::GetFullPath($RunDir)
$script:PYMERCATOR_RUNTIME_DIR = $RunDir
$script:PYMERCATOR_MANIFEST_PATH = Join-Path $RunDir "review_manifest.json"
$script:PYMERCATOR_MANIFEST = [ordered]@{
    schema_version = "runtime_manifest.v1"
    script         = $scriptName
    created_at     = (Get-Date).ToUniversalTime().ToString("o")
    project_root   = $script:PROJECT_ROOT
    python         = [ordered]@{
        executable = $script:PY
        version    = $script:PYTHON_VERSION
    }
    git            = [ordered]@{
        branch = $script:GIT_INFO.branch
        commit = $script:GIT_INFO.commit
        dirty  = [bool]$script:GIT_INFO.dirty
    }
    source_run_dir = $RunDir
    commands       = @()
    outputs        = [ordered]@{}
    status         = "RUNNING"
}
$null = Write-RunManifest -Status "RUNNING"
$listName = $script:PYMERCATOR_DEFAULT_LIST
$reportJson = Join-Path $RunDir "report_${Profile}.json"
$updateLog = Join-Path $RunDir "05_review_update.log"
$reviewLog = Join-Path $RunDir "06_observation_review.log"
$reviewTxt = Join-Path $RunDir "observation_review.txt"
$reviewCsv = Join-Path $RunDir "observation_review.csv"
$reviewJson = Join-Path $RunDir "observation_review.json"
$reviewManifest = $script:PYMERCATOR_MANIFEST_PATH

if (-not (Test-Path -LiteralPath $reportJson)) {
    throw "Report JSON not found: $reportJson"
}

Write-PyMercatorRuntimeHeader -Title "PYMERCATOR DAILY REVIEW"

if (-not $SkipUpdate) {
    $updateResult = Invoke-PyMercatorStep `
        -Python $PY `
        -Name "Refresh $listName prices for review" `
        -PyArgs @("update", "--list", $listName) `
        -LogFile $updateLog `
        -Critical $false

    $updateCode = [int](@($updateResult) | Select-Object -Last 1)
    if ($updateCode -ne 0) {
        Write-Host ""
        Write-Host "FAILED: price refresh for review." -ForegroundColor Red
        Write-Host "LOG   : $updateLog"
        $null = Write-RunManifest -Status "FAIL" -Outputs @{
            report_json = $reportJson
            update_log  = $updateLog
            manifest    = $reviewManifest
        }
        Show-PyMercatorLogTail -LogFile $updateLog -Lines 80
        exit $updateCode
    }
}

$capitalText = $Capital.ToString([System.Globalization.CultureInfo]::InvariantCulture)
$reviewResult = Invoke-PyMercatorStep `
    -Python $PY `
    -Name "MTM observation review" `
    -PyArgs @(
    "mtm",
    "--run-dir",
    $RunDir,
    "--capital",
    $capitalText,
    "--mode",
    $Mode,
    "--profile",
    $Profile,
    "--prices-dir",
    $PricesDir
) `
    -LogFile $reviewLog

$reviewCode = [int](@($reviewResult) | Select-Object -Last 1)

Remove-AnsiFromFile -Path $reviewTxt
Remove-AnsiFromFile -Path $reviewCsv
Remove-AnsiFromFile -Path $reviewJson
Remove-AnsiFromFile -Path $reviewLog

if (Test-Path -LiteralPath $reviewTxt) {
    Write-Host ""
    Get-Content -LiteralPath $reviewTxt | ForEach-Object { Write-Host $_ }
}

$reviewStatus = ""
if (Test-Path -LiteralPath $reviewJson) {
    try {
        $reviewPayload = Get-Content -LiteralPath $reviewJson -Raw | ConvertFrom-Json
        if ($null -ne $reviewPayload.status -and $reviewPayload.status -eq "NOT_COMPUTED") {
            $reviewStatus = "NOT_COMPUTED"
        }
    }
    catch {
        # ignore invalid JSON
    }
}

if ((-not $reviewStatus) -and (Test-Path -LiteralPath $reviewTxt)) {
    $txtContent = Get-Content -LiteralPath $reviewTxt -Raw
    if ($txtContent -match "status\s*NOT_COMPUTED") {
        $reviewStatus = "NOT_COMPUTED"
    }
}

$outputs = @{
    review_txt  = $reviewTxt
    review_csv  = $reviewCsv
    review_json = $reviewJson
    report_json = $reportJson
    review_log  = $reviewLog
    manifest    = $reviewManifest
}
if (-not $SkipUpdate) {
    $outputs["update_log"] = $updateLog
}

$manifestStatus = if ($reviewCode -ne 0) { "FAIL" } else { "OK" }
$null = Write-RunManifest -Status $manifestStatus -Outputs $outputs

$finalMessage = if ($reviewStatus -eq "NOT_COMPUTED") {
    "DAILY REVIEW NOT COMPUTED"
}
elseif ($reviewCode -ne 0) {
    "DAILY REVIEW FAILED"
}
else {
    "DAILY REVIEW FINISHED"
}

Write-Host ""
Write-Host "============================================================"
Write-Host $finalMessage
Write-Host "RUNTIME: $RunDir"
Write-Host "REPORT : $reviewTxt"
Write-Host "============================================================"
