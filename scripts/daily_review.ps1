param(
    [string]$PY = "",
    [string]$Profile = "CON",
    [string]$List = "IBOV",
    [string]$SignalDate = "",
    [string]$ReviewDate = "",
    [string]$SignalsDir = "storage/signals",
    [string]$PricesDir = "data/prices",
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
    signal_date = $SignalDate
    review_date = $ReviewDate
    signals_dir = $SignalsDir
    prices_dir = $PricesDir
    emit_json = $Json.IsPresent
} | ConvertTo-Json -Compress

$env:AURUM_CORE_ARGS = $argsPayload
$code = @'
import json
import os
import sys
from pathlib import Path

from aurum.core import run_review

args = json.loads(os.environ["AURUM_CORE_ARGS"])
emit_json = bool(args.pop("emit_json", False))
for key in ("signal_date", "review_date"):
    if not args.get(key):
        args[key] = None

try:
    payload = run_review(**args)
except FileNotFoundError as exc:
    profile = str(args.get("profile") or "CON").upper()
    list_name = str(args.get("list_name") or "IBOV").upper()
    signals_dir = Path(str(args.get("signals_dir") or "storage/signals"))
    latest = ""
    if signals_dir.exists():
        stem = f"{profile}_{list_name}_signal.json"
        matches = sorted(path for path in signals_dir.glob(f"*/{stem}") if path.is_file())
        if matches:
            latest = matches[-1].parent.name

    print("AURUM REVIEW | SNAPSHOT NOT FOUND", file=sys.stderr)
    print(str(exc), file=sys.stderr)
    if latest:
        print(
            f"Snapshot encontrado para {latest}. Para revisar esse dia, rode: "
            f"scripts\\daily_review.ps1 -SignalDate {latest}",
            file=sys.stderr,
        )
    else:
        print(
            "Rode scripts\\daily_signal.ps1 primeiro para criar "
            "storage\\signals\\YYYY-MM-DD\\PROFILE_LIST_signal.json.",
            file=sys.stderr,
        )
    raise SystemExit(2)

if emit_json:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
else:
    print(payload["text"], end="")
'@

try {
    $tempPy = Join-Path ([System.IO.Path]::GetTempPath()) ("aurum_daily_review_{0}.py" -f ([guid]::NewGuid().ToString("N")))
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
