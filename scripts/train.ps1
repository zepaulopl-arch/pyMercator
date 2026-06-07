param(
    [switch]$Details,
    [switch]$Color
)

$ErrorActionPreference = "Stop"

$OpsCommon = Join-Path $PSScriptRoot "ops_common.ps1"
if (Test-Path $OpsCommon) {
    . $OpsCommon
}

if (Get-Command Initialize-PyMercatorScript -ErrorAction SilentlyContinue) {
    Initialize-PyMercatorScript
}

if (Get-Command Show-PyMercatorProfileSummary -ErrorAction SilentlyContinue) {
    Show-PyMercatorProfileSummary
}

if ($Color) {
    $env:AURUM_COLOR = "1"
}

$cmd = @("-m", "pymercator", "train", "run")

if ($Details) {
    $cmd += "--details"
}

if (Get-Command Invoke-AurumCommand -ErrorAction SilentlyContinue) {
    $null = Invoke-AurumCommand -Command $cmd
    $ExitCode = $LASTEXITCODE
} else {
    python @cmd
    $ExitCode = $LASTEXITCODE
}

if (Get-Command Write-RunManifest -ErrorAction SilentlyContinue) {
    try {
        Write-RunManifest -Name "train" -ExitCode $ExitCode
    } catch {
        Write-Host "WARN Write-RunManifest failed: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

exit $ExitCode
