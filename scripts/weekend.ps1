param(
    [switch]$NoAutotune,
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

if ($Color) {
    $env:AURUM_COLOR = "1"
}

$cmd = @("-m", "pymercator", "weekend", "run")

if ($NoAutotune) {
    $cmd += "--no-autotune"
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
        Write-RunManifest -Name "weekend" -ExitCode $ExitCode
    } catch {
        Write-Host "WARN Write-RunManifest failed: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

exit $ExitCode
