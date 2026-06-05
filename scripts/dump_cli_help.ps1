param(
    [string]$PY = ""
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "ops_common.ps1")

$scriptName = Split-Path -Leaf $PSCommandPath
$PY = Initialize-PyMercatorScript -RequestedPython $PY -ScriptName $scriptName
Set-PyMercatorColorMode -Enabled $false

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outputDir = Join-Path "runtime" "cli_help_$timestamp"
$outputFile = Join-Path $outputDir "help_index.txt"
$null = New-Item -ItemType Directory -Force -Path $outputDir

$commands = @(
    @{ Label = "python -m pymercator --help"; Args = @("--help") },
    @{ Label = "python -m pymercator update --help"; Args = @("update", "--help") },
    @{ Label = "python -m pymercator diag --help"; Args = @("diag", "--help") },
    @{ Label = "python -m pymercator train --help"; Args = @("train", "--help") },
    @{ Label = "python -m pymercator train benchmark-engines --help"; Args = @("train", "benchmark-engines", "--help") },
    @{ Label = "python -m pymercator run --help"; Args = @("run", "--help") },
    @{ Label = "python -m pymercator db --help"; Args = @("db", "--help") },
    @{ Label = "python -m pymercator db status --help"; Args = @("db", "status", "--help") },
    @{ Label = "python -m pymercator db last-run --help"; Args = @("db", "last-run", "--help") },
    @{ Label = "python -m pymercator db signal --help"; Args = @("db", "signal", "--help") },
    @{ Label = "python -m pymercator db rank-last --help"; Args = @("db", "rank-last", "--help") },
    @{ Label = "python -m pymercator db sim-last --help"; Args = @("db", "sim-last", "--help") },
    @{ Label = "python -m pymercator observe --help"; Args = @("observe", "--help") },
    @{ Label = "python -m pymercator basket --help"; Args = @("basket", "--help") },
    @{ Label = "python -m pymercator mtm --help"; Args = @("mtm", "--help") },
    @{ Label = "python -m pymercator review --help"; Args = @("review", "--help") },
    @{ Label = "python -m pymercator universe --help"; Args = @("universe", "--help") },
    @{ Label = "python -m pymercator scenario --help"; Args = @("scenario", "--help") },
    @{ Label = "python -m pymercator context --help"; Args = @("context", "--help") },
    @{ Label = "python -m pymercator borrow --help"; Args = @("borrow", "--help") },
    @{ Label = "python -m pymercator pos --help"; Args = @("pos", "--help") },
    @{ Label = "python -m pymercator prices --help"; Args = @("prices", "--help") },
    @{ Label = "python -m pymercator lab --help"; Args = @("lab", "--help") },
    @{ Label = "python -m pymercator cfg --help"; Args = @("cfg", "--help") },
    @{ Label = "python -m pymercator open --help"; Args = @("open", "--help") },
    @{ Label = "python -m pymercator daily --help"; Args = @("daily", "--help") },
    @{ Label = "python -m pymercator execution --help"; Args = @("execution", "--help") },
    @{ Label = "python -m pymercator indices --help"; Args = @("indices", "--help") },
    @{ Label = "python -m pymercator sentiment --help"; Args = @("sentiment", "--help") },
    @{ Label = "python -m pymercator predict --help"; Args = @("predict", "--help") },
    @{ Label = "python -m pymercator features --help"; Args = @("features", "--help") }
)

$lines = [System.Collections.Generic.List[string]]::new()
[void]$lines.Add("PYMERCATOR CLI HELP")
[void]$lines.Add("Generated at: $((Get-Date).ToUniversalTime().ToString("o"))")
[void]$lines.Add("Python: $PY")
[void]$lines.Add("")

foreach ($item in $commands) {
    [void]$lines.Add("================================================================================")
    [void]$lines.Add($item.Label)
    [void]$lines.Add("--------------------------------------------------------------------------------")

    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $PY -m pymercator @($item.Args) 2>&1
        $exitCode = $LASTEXITCODE
    } catch {
        $output = @("$_")
        $exitCode = 1
    } finally {
        $ErrorActionPreference = $previousPreference
    }

    if ($exitCode -ne 0) {
        [void]$lines.Add("STATUS: NOT_AVAILABLE")
        [void]$lines.Add("EXIT_CODE: $exitCode")
    } else {
        [void]$lines.Add("STATUS: OK")
    }

    foreach ($line in @($output)) {
        [void]$lines.Add("$line")
    }
    [void]$lines.Add("")
}

Set-Content -LiteralPath $outputFile -Value $lines -Encoding UTF8
Remove-AnsiFromFile -Path $outputFile
Write-Host "CLI help written: $outputFile"
