param(
    [string]$Profile = "CON",
    [int]$Top = 10,
    [string]$List = "IBOV",
    [switch]$Basket,
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

$cmd = @(
    "-m", "pymercator",
    "signal", "run",
    "--profile", $Profile,
    "--top", "$Top",
    "--list", $List
)

if ($Basket) {
    $cmd += "--basket"
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
        Write-RunManifest -Name "signal" -ExitCode $ExitCode
    } catch {
        Write-Host "WARN Write-RunManifest failed: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

exit $ExitCode



# Runtime manifest/report hook
if (Get-Command Show-PyMercatorSignals -ErrorAction SilentlyContinue) {
    Show-PyMercatorSignals
}
