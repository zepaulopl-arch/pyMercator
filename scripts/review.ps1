param(
    [string]$Profile = "CON",
    [string]$List = "IBOV"
)

$ErrorActionPreference = "Stop"

$OpsCommon = Join-Path $PSScriptRoot "ops_common.ps1"
if (Test-Path $OpsCommon) {
    . $OpsCommon
}

$RuntimeConfig = $null
if (Get-Command Get-AurumRuntimeConfig -ErrorAction SilentlyContinue) {
    $RuntimeConfig = Get-AurumRuntimeConfig
} elseif (Get-Command Get-RuntimeConfig -ErrorAction SilentlyContinue) {
    $RuntimeConfig = Get-RuntimeConfig
}


python -m pymercator review run --profile $Profile --list $List
exit $LASTEXITCODE
