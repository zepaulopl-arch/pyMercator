param([string]$Python = "")

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "ops_common.ps1")

$Python = Initialize-PyMercatorScript -RequestedPython $Python
$logDir = New-PyMercatorLogDir -Prefix "daily_profiles"
$UseColor = (-not [Console]::IsOutputRedirected) -and (-not $env:NO_COLOR)
$profiles = @(
    @{ Name = "CON"; Prefix = "01" },
    @{ Name = "BAL"; Prefix = "02" },
    @{ Name = "AGR"; Prefix = "03" },
    @{ Name = "RLX"; Prefix = "04" }
)

function Get-ProfileArtifactPaths {
    param(
        [string]$Profile,
        [string]$Prefix
    )

    return @{
        Log = Join-Path $logDir "${Prefix}_run_${Profile}.txt"
        Report = Join-Path $logDir "${Prefix}_report_${Profile}.txt"
        Json = Join-Path $logDir "${Prefix}_report_${Profile}.json"
        RunDir = Join-Path $logDir "${Prefix}_run_${Profile}"
        Basket = Join-Path $logDir "${Prefix}_basket_${Profile}.csv"
    }
}

function Read-ProfileJson {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    try {
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    } catch {
        Write-Host "WARNING: failed to read profile JSON: $Path" -ForegroundColor Yellow
        return $null
    }
}

function Test-DecisionCode {
    param(
        [object]$Decision,
        [string]$Code
    )

    $codes = @()
    if ($Decision.decision_codes) {
        $codes += @($Decision.decision_codes)
    }
    if ($Decision.blocker_reasons) {
        $codes += @($Decision.blocker_reasons)
    }
    return ($codes -contains $Code)
}

function Get-DecisionStatus {
    param([object]$Decision)

    if ($Decision.permission -and $Decision.permission.status) {
        return [string]$Decision.permission.status
    }
    if ($Decision.status) {
        return [string]$Decision.status
    }
    return ""
}

function Get-ProfileSummary {
    param(
        [string]$Profile,
        [object]$Payload
    )

    $decisions = @()
    if ($Payload -and $Payload.decisions) {
        $decisions = @($Payload.decisions)
    }

    $summary = [ordered]@{
        Profile = $Profile
        Actionable = 0
        Watch = 0
        Blocked = 0
        CtxLow = 0
        VolHigh = 0
        AtrHigh = 0
        RrLow = 0
        Basket = "-"
        Blockers = @{}
    }

    foreach ($decision in $decisions) {
        $status = (Get-DecisionStatus -Decision $decision).ToUpperInvariant()
        if ($status -eq "READY") {
            $summary.Actionable += 1
        } elseif ($status -eq "WATCH") {
            $summary.Watch += 1
        } elseif ($status -eq "BLOCKED") {
            $summary.Blocked += 1
        }

        if (Test-DecisionCode -Decision $decision -Code "CTX_LOW") {
            $summary.CtxLow += 1
        }
        if (Test-DecisionCode -Decision $decision -Code "VOL_HIGH") {
            $summary.VolHigh += 1
        }
        if (Test-DecisionCode -Decision $decision -Code "ATR_HIGH") {
            $summary.AtrHigh += 1
        }
        if (Test-DecisionCode -Decision $decision -Code "RR_LOW") {
            $summary.RrLow += 1
        }
    }

    if ($Payload -and $Payload.basket -and $Payload.basket.status) {
        $summary.Basket = [string]$Payload.basket.status
    }

    $blockers = @{}
    if ($Payload -and $Payload.blockers_count) {
        $blockers = $Payload.blockers_count
    } elseif ($Payload -and $Payload.blockers) {
        $blockers = $Payload.blockers
    }
    if ($blockers -is [System.Collections.IDictionary]) {
        foreach ($key in $blockers.Keys) {
            $summary.Blockers[$key] = [int]$blockers[$key]
        }
    } else {
        foreach ($item in $blockers.PSObject.Properties) {
            $summary.Blockers[$item.Name] = [int]$item.Value
        }
    }

    return [pscustomobject]$summary
}

function Get-StatusColor {
    param([string]$Status)

    switch ($Status.ToUpperInvariant()) {
        "OK" { return "Green" }
        "READY" { return "Green" }
        "ACTIONABLE" { return "Green" }
        "WATCH" { return "Yellow" }
        "DEGRADED" { return "Yellow" }
        "BLOCKED" { return "Red" }
        "FAIL" { return "Red" }
        "AVOID" { return "Red" }
        "MODEL_WEAK" { return "Red" }
        "RISK_OFF" { return "Red" }
        "BEHAVIOR_AVOID" { return "Red" }
        default { return "Gray" }
    }
}

function Format-ProfileSummaryHeader {
    return "{0,-7} {1,10} {2,6} {3,8} {4,8} {5,9} {6,9} {7,7}  {8,-8}" -f `
        "PROFILE", "ACTIONABLE", "WATCH", "BLOCKED", "CTX_LOW", "VOL_HIGH", `
        "ATR_HIGH", "RR_LOW", "BASKET"
}

function Format-ProfileSummaryLine {
    param([object]$Summary)

    return "{0,-7} {1,10} {2,6} {3,8} {4,8} {5,9} {6,9} {7,7}  {8,-8}" -f `
        $Summary.Profile, $Summary.Actionable, $Summary.Watch, $Summary.Blocked, `
        $Summary.CtxLow, $Summary.VolHigh, $Summary.AtrHigh, $Summary.RrLow, `
        $Summary.Basket
}

function Write-ProfileSummaryLine {
    param([object]$Summary)

    $prefix = "{0,-7} {1,10} {2,6} {3,8} {4,8} {5,9} {6,9} {7,7}  " -f `
        $Summary.Profile, $Summary.Actionable, $Summary.Watch, $Summary.Blocked, `
        $Summary.CtxLow, $Summary.VolHigh, $Summary.AtrHigh, $Summary.RrLow
    $basket = "{0,-8}" -f $Summary.Basket

    if ($UseColor) {
        Write-Host $prefix -NoNewline
        Write-Host $basket -ForegroundColor (Get-StatusColor -Status $Summary.Basket)
    } else {
        Write-Host "$prefix$basket"
    }
}

function Get-GlobalBlockers {
    param([object[]]$Summaries)

    $counts = @{}
    $globalPriority = @("MODEL_WEAK", "RISK_OFF", "BEHAVIOR_AVOID")
    foreach ($summary in $Summaries) {
        foreach ($item in $summary.Blockers.GetEnumerator()) {
            if (-not $counts.ContainsKey($item.Key)) {
                $counts[$item.Key] = 0
            }
            $counts[$item.Key] += [int]$item.Value
        }
    }

    $global = @($globalPriority | Where-Object {
        $counts.ContainsKey($_) -and $counts[$_] -gt 0
    })
    if ($global.Count -gt 0) {
        return $global
    }

    return $counts.GetEnumerator() |
        Where-Object { $_.Value -gt 0 } |
        Sort-Object -Property `
            @{ Expression = { $_.Value }; Descending = $true },
            @{ Expression = { $_.Key }; Ascending = $true } |
        Select-Object -First 3 |
        ForEach-Object { $_.Key }
}

function Write-BlockerVerdict {
    param([string[]]$Blockers)

    if (-not $Blockers -or $Blockers.Count -eq 0) {
        Write-Host "No global blockers dominate."
        return
    }

    if (-not $UseColor) {
        Write-Host "Global blockers dominate: $($Blockers -join ', ')."
        return
    }

    Write-Host "Global blockers dominate: " -NoNewline
    for ($index = 0; $index -lt $Blockers.Count; $index += 1) {
        if ($index -gt 0) {
            Write-Host ", " -NoNewline
        }
        $blocker = $Blockers[$index]
        Write-Host $blocker -ForegroundColor (Get-StatusColor -Status $blocker) -NoNewline
    }
    Write-Host "."
}

function Write-ProfileSummary {
    param([object[]]$Summaries)

    $rows = @($Summaries | Where-Object { $null -ne $_ })
    $plainLines = New-Object System.Collections.Generic.List[string]
    $plainLines.Add("")
    $plainLines.Add("PROFILE SUMMARY")
    $plainLines.Add("--------------------------------------------------------------------------------")
    $plainLines.Add((Format-ProfileSummaryHeader))

    Write-Host ""
    Write-Host "PROFILE SUMMARY"
    Write-Host "--------------------------------------------------------------------------------"
    Write-Host (Format-ProfileSummaryHeader)

    if ($rows.Count -eq 0) {
        $message = "No profile summaries available."
        $plainLines.Add($message)
        Write-Host $message
        $summaryLog = Join-Path $logDir "profile_summary.txt"
        $plainLines | Set-Content -LiteralPath $summaryLog -Encoding UTF8
        return
    }

    foreach ($summary in $rows) {
        $plainLines.Add((Format-ProfileSummaryLine -Summary $summary))
        Write-ProfileSummaryLine -Summary $summary
    }

    $actionable = @($rows | Where-Object { $_.Actionable -gt 0 })
    $blockers = @(Get-GlobalBlockers -Summaries $rows)

    $plainLines.Add("")
    $plainLines.Add("VERDICT")
    $plainLines.Add("--------------------------------------------------------------------------------")
    Write-Host ""
    Write-Host "VERDICT"
    Write-Host "--------------------------------------------------------------------------------"

    if ($actionable.Count -gt 0) {
        $allowed = $actionable | ForEach-Object { "$($_.Profile)=$($_.Actionable)" }
        $message = "At least one profile allowed trades: $($allowed -join ', ')."
        $plainLines.Add($message)
        if ($UseColor) {
            Write-Host $message -ForegroundColor Green
        } else {
            Write-Host $message
        }
    } else {
        $message = "No profile allowed trades."
        $plainLines.Add($message)
        Write-Host $message
    }

    if ($blockers.Count -gt 0) {
        $plainLines.Add("Global blockers dominate: $($blockers -join ', ').")
    } else {
        $plainLines.Add("No global blockers dominate.")
    }
    Write-BlockerVerdict -Blockers $blockers

    $summaryLog = Join-Path $logDir "profile_summary.txt"
    $plainLines | Set-Content -LiteralPath $summaryLog -Encoding UTF8
}

Write-Host ""
Write-Host "PYMERCATOR DAILY PROFILE COMPARISON"
Write-Host "PYTHON : $Python"
Write-Host "LOG DIR: $logDir"
Write-Host ""

Invoke-PyMercatorStep `
    -Python $Python `
    -Name "Update IBOV" `
    -PyArgs @("update", "--list", "IBOV") `
    -LogFile (Join-Path $logDir "00_update.txt") `
    -Critical $false

$summaries = New-Object System.Collections.ArrayList

foreach ($profile in $profiles) {
    $profileName = [string]$profile["Name"]
    $profilePrefix = [string]$profile["Prefix"]
    $paths = Get-ProfileArtifactPaths -Profile $profileName -Prefix $profilePrefix
    Invoke-PyMercatorStep `
        -Python $Python `
        -Name "Run $profileName basket" `
        -PyArgs @(
            "run",
            "--profile",
            $profileName,
            "--basket",
            "--report-output",
            $paths.Report,
            "--json-output",
            $paths.Json,
            "--run-dir",
            $paths.RunDir,
            "--basket-output",
            $paths.Basket
        ) `
        -LogFile $paths.Log

    $payload = Read-ProfileJson -Path $paths.Json
    [void]$summaries.Add((Get-ProfileSummary -Profile $profileName -Payload $payload))
}

Write-ProfileSummary -Summaries @($summaries.ToArray())

Write-Host ""
Write-Host "============================================================"
Write-Host "DAILY PROFILE COMPARISON FINISHED"
Write-Host "LOGS: $logDir"
Write-Host "============================================================"
