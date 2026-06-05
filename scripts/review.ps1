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

if ($PY -eq "--capital") {
    $Capital = [double]::Parse($RunDir, [System.Globalization.CultureInfo]::InvariantCulture)
    $PY = ""
    $RunDir = ""
}

$forward = @{
    Capital = $Capital
    Mode = $Mode
    Profile = $Profile
    PricesDir = $PricesDir
}
if ($PY) {
    $forward["PY"] = $PY
}
if ($RunDir) {
    $forward["RunDir"] = $RunDir
}
if ($Color) {
    $forward["Color"] = $true
}
if ($SkipUpdate) {
    $forward["SkipUpdate"] = $true
}

& (Join-Path $PSScriptRoot "run_daily_review.ps1") @forward
