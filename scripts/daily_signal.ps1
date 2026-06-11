param(
    [string]$PY = "",
    [string]$Profile = "CON",
    [string]$List = "IBOV",
    [double]$Capital = 100000.0,
    [int]$Slots = 5,
    [string]$SignalDate = "",
    [string]$SignalsDir = "storage/signals",
    [string]$PricesDir = "data/prices",
    [switch]$NoUpdate,
    [switch]$Force,
    [switch]$Json,
    [switch]$Color
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "ops_common.ps1")

$scriptName = Split-Path -Leaf $PSCommandPath
$PY = Initialize-AurumScript -RequestedPython $PY -ScriptName $scriptName
Set-AurumColorMode -Enabled $Color.IsPresent

$argsPayload = @{
    profile = $Profile
    list_name = $List
    capital = $Capital
    slots = $Slots
    signal_date = $SignalDate
    signals_dir = $SignalsDir
    prices_dir = $PricesDir
    update = (-not $NoUpdate.IsPresent)
    force = $Force.IsPresent
    emit_json = $Json.IsPresent
} | ConvertTo-Json -Compress

$env:AURUM_CORE_ARGS = $argsPayload
$code = @'
import json
import os

from aurum.core import run_daily

args = json.loads(os.environ["AURUM_CORE_ARGS"])
emit_json = bool(args.pop("emit_json", False))
if not args.get("signal_date"):
    args["signal_date"] = None

payload = run_daily(**args)
if emit_json:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
else:
    print(payload["text"], end="")
'@

try {
    $tempPy = Join-Path ([System.IO.Path]::GetTempPath()) ("aurum_daily_signal_{0}.py" -f ([guid]::NewGuid().ToString("N")))
    Set-Content -LiteralPath $tempPy -Value $code -Encoding UTF8
    & $PY $tempPy
    $exitCode = $LASTEXITCODE
} finally {
    if ($tempPy -and (Test-Path -LiteralPath $tempPy)) {
        Remove-Item -LiteralPath $tempPy -Force -ErrorAction SilentlyContinue
    }
    Remove-Item Env:\AURUM_CORE_ARGS -ErrorAction SilentlyContinue
}

if ($exitCode -ne 0) {
    Write-RunManifest -Status "FAIL" -Outputs @{ signals_dir = $SignalsDir; list = $List; profile = $Profile }
    exit $exitCode
}

Write-RunManifest -Status "OK" -Outputs @{ signals_dir = $SignalsDir; list = $List; profile = $Profile }
exit 0
