param(
    [string]$PY = "",
    [string]$List = "IBOV",
    [string]$Output = "storage/reports/latest_weekly_report.txt",
    [string]$Matrix = "storage/features/latest_feature_matrix.csv",
    [string]$Universe = "data/universes/ibov_live.csv",
    [string]$PricesDir = "data/prices",
    [string]$DatasetOutput = "storage/prediction/latest_dataset.csv",
    [string]$EvaluationOutput = "storage/prediction/latest_evaluation.json",
    [switch]$NoUpdate,
    [switch]$NoTrain,
    [switch]$Json,
    [switch]$Color
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "ops_common.ps1")

$scriptName = Split-Path -Leaf $PSCommandPath
$PY = Initialize-AurumScript -RequestedPython $PY -ScriptName $scriptName
Set-AurumColorMode -Enabled $Color.IsPresent

$argsPayload = @{
    list_name = $List
    output = $Output
    update = (-not $NoUpdate.IsPresent)
    train = (-not $NoTrain.IsPresent)
    matrix = $Matrix
    universe = $Universe
    prices_dir = $PricesDir
    dataset_output = $DatasetOutput
    evaluation_output = $EvaluationOutput
    emit_json = $Json.IsPresent
} | ConvertTo-Json -Compress

$env:AURUM_CORE_ARGS = $argsPayload
$code = @'
import json
import os

from aurum.core import run_weekly

args = json.loads(os.environ["AURUM_CORE_ARGS"])
emit_json = bool(args.pop("emit_json", False))

payload = run_weekly(**args)
if emit_json:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
else:
    print(payload["text"], end="")
'@

try {
    $tempPy = Join-Path ([System.IO.Path]::GetTempPath()) ("aurum_weekly_train_{0}.py" -f ([guid]::NewGuid().ToString("N")))
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
    Write-RunManifest -Status "FAIL" -Outputs @{ weekly_report = $Output; list = $List }
    exit $exitCode
}

Write-RunManifest -Status "OK" -Outputs @{ weekly_report = $Output; list = $List }
exit 0
