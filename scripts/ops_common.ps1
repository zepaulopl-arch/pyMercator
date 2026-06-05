$ErrorActionPreference = "Stop"

$script:PY = ""
$script:PROJECT_ROOT = ""
$script:PYTHON_VERSION = ""
$script:PYMERCATOR_DEFAULT_LIST = "IBOV"
$script:PYMERCATOR_COLOR = "never"
$script:GIT_INFO = $null
$script:PYMERCATOR_RUNTIME_DIR = ""
$script:PYMERCATOR_MANIFEST_PATH = ""
$script:PYMERCATOR_MANIFEST = $null
$script:PYMERCATOR_SCRIPT_NAME = ""
$script:PYMERCATOR_VT_ATTEMPTED = $false

function Enable-PyMercatorVirtualTerminal {
    if ($script:PYMERCATOR_VT_ATTEMPTED) {
        return
    }
    $script:PYMERCATOR_VT_ATTEMPTED = $true

    $source = @"
using System;
using System.Runtime.InteropServices;

public static class PyMercatorConsoleMode {
    [DllImport("kernel32.dll")]
    private static extern IntPtr GetStdHandle(int nStdHandle);

    [DllImport("kernel32.dll")]
    private static extern bool GetConsoleMode(IntPtr hConsoleHandle, out int lpMode);

    [DllImport("kernel32.dll")]
    private static extern bool SetConsoleMode(IntPtr hConsoleHandle, int dwMode);

    public static void EnableVirtualTerminal() {
        IntPtr handle = GetStdHandle(-11);
        int mode;
        if (GetConsoleMode(handle, out mode)) {
            SetConsoleMode(handle, mode | 0x0004);
        }
    }
}
"@
    try {
        Add-Type -TypeDefinition $source -ErrorAction SilentlyContinue | Out-Null
        [PyMercatorConsoleMode]::EnableVirtualTerminal()
    } catch {
        return
    }
}

function Set-PyMercatorColorMode {
    param([bool]$Enabled = $false)

    if ($Enabled) {
        $script:PYMERCATOR_COLOR = "always"
        Remove-Item Env:\NO_COLOR -ErrorAction SilentlyContinue
        Remove-Item Env:\PY_COLORS -ErrorAction SilentlyContinue
        $env:FORCE_COLOR = "1"
        $env:CLICOLOR = "1"
        $env:TERM = "xterm-256color"
        Enable-PyMercatorVirtualTerminal
    } else {
        $script:PYMERCATOR_COLOR = "never"
        $env:NO_COLOR = "1"
        $env:PY_COLORS = "0"
        Remove-Item Env:\FORCE_COLOR -ErrorAction SilentlyContinue
        $env:CLICOLOR = "0"
    }
}

function Get-PyMercatorColorArgs {
    if ($script:PYMERCATOR_COLOR -and $script:PYMERCATOR_COLOR -ne "never") {
        return @("--color", $script:PYMERCATOR_COLOR)
    }
    return @("--no-color")
}

function Remove-AnsiFromFile {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    $ansiPattern = "`e\[[0-?]*[ -/]*[@-~]"
    $content = Get-Content -LiteralPath $Path -Raw
    $clean = $content -replace $ansiPattern, ""
    if ($clean -ne $content) {
        Set-Content -LiteralPath $Path -Value $clean -Encoding UTF8
    }
}

function Get-PyMercatorJsonValue {
    param(
        [object]$Object,
        [string]$Name,
        [object]$Default = 0
    )

    if ($null -eq $Object) {
        return $Default
    }
    if ($Object.PSObject.Properties.Name -contains $Name) {
        return $Object.$Name
    }
    return $Default
}

function Get-PyMercatorProfilePaths {
    param(
        [string]$LogDir,
        [string]$Profile
    )

    return @{
        Report = Join-Path $LogDir "report_${Profile}.txt"
        Json = Join-Path $LogDir "report_${Profile}.json"
        RunDir = Join-Path $LogDir "run_${Profile}"
        Basket = Join-Path $LogDir "basket_${Profile}.csv"
        Log = Join-Path $LogDir "run_${Profile}.log"
    }
}

function Show-PyMercatorProfileSummary {
    param(
        [string]$LogDir,
        [string[]]$Profiles,
        [switch]$SkipVerdict
    )

    $rows = @()
    $blockers = @{}
    $script:PYMERCATOR_LAST_PROFILE_SUMMARY = $null
    foreach ($profile in $Profiles) {
        $paths = Get-PyMercatorProfilePaths -LogDir $LogDir -Profile $profile
        $payload = $null
        if (Test-Path -LiteralPath $paths.Json) {
            try {
                $payload = Get-Content -LiteralPath $paths.Json -Raw | ConvertFrom-Json
            } catch {
                Write-Host "WARNING: unable to parse profile JSON for ${profile}: $($paths.Json)" -ForegroundColor Yellow
                $payload = $null
            }
        } else {
            Write-Host "WARNING: missing profile JSON for ${profile}: $($paths.Json)" -ForegroundColor Yellow
        }

        $decision = Get-PyMercatorJsonValue -Object $payload -Name "decision" -Default $null
        $decisions = @(Get-PyMercatorJsonValue -Object $payload -Name "decisions" -Default @())
        $basketPayload = Get-PyMercatorJsonValue -Object $payload -Name "basket" -Default $null
        $blockerPayload = Get-PyMercatorJsonValue -Object $payload -Name "blockers_count" -Default $null
        if ($null -eq $blockerPayload) {
            $blockerPayload = Get-PyMercatorJsonValue -Object $payload -Name "blockers" -Default $null
        }

        $volHigh = 0
        $atrHigh = 0
        foreach ($item in $decisions) {
            $codes = @(Get-PyMercatorJsonValue -Object $item -Name "decision_codes" -Default @())
            if ($codes -contains "VOL_HIGH") {
                $volHigh += 1
            }
            if ($codes -contains "ATR_HIGH") {
                $atrHigh += 1
            }
        }

        if ($null -ne $blockerPayload) {
            foreach ($prop in $blockerPayload.PSObject.Properties) {
                $current = 0
                if ($blockers.ContainsKey($prop.Name)) {
                    $current = [int]$blockers[$prop.Name]
                }
                $blockers[$prop.Name] = $current + [int]$prop.Value
            }
        }

        $rows += [pscustomobject]@{
            Profile = $profile
            Actionable = [int](Get-PyMercatorJsonValue -Object $decision -Name "actionable" -Default 0)
            Watch = [int](Get-PyMercatorJsonValue -Object $decision -Name "watch" -Default 0)
            Blocked = [int](Get-PyMercatorJsonValue -Object $decision -Name "blocked" -Default 0)
            VolHigh = $volHigh
            AtrHigh = $atrHigh
            Basket = [string](Get-PyMercatorJsonValue -Object $basketPayload -Name "status" -Default "-")
        }
    }

    Write-Host ""
    Write-Host "PROFILE SUMMARY"
    Write-Host "--------------------------------------------------------------------------------"
    Write-Host ("{0,-7} {1,10} {2,6} {3,8} {4,9} {5,9} {6,9}" -f "PROFILE", "ACTIONABLE", "WATCH", "BLOCKED", "VOL_HIGH", "ATR_HIGH", "BASKET")
    foreach ($row in $rows) {
        Write-Host ("{0,-7} {1,10} {2,6} {3,8} {4,9} {5,9} {6,9}" -f $row.Profile, $row.Actionable, $row.Watch, $row.Blocked, $row.VolHigh, $row.AtrHigh, $row.Basket)
    }

    $totalActionable = ($rows | Measure-Object -Property Actionable -Sum).Sum
    $globalBlockers = @()
    $secondaryBlockers = @()
    if ($blockers.Count -gt 0) {
        $secondaryCodes = @("VOL_HIGH", "ATR_HIGH")
        $globalBlockers = $blockers.GetEnumerator() |
            Where-Object { $secondaryCodes -notcontains $_.Name } |
            Sort-Object -Property @{ Expression = { [int]$_.Value }; Descending = $true }, Name |
            Select-Object -First 3 |
            ForEach-Object { $_.Name }
        $secondaryBlockers = $secondaryCodes | Where-Object {
            $blockers.ContainsKey($_) -and [int]$blockers[$_] -gt 0
        }
    }

    $script:PYMERCATOR_LAST_PROFILE_SUMMARY = [pscustomobject]@{
        TotalActionable = [int]$totalActionable
        GlobalBlockers = @($globalBlockers)
        SecondaryBlockers = @($secondaryBlockers)
    }

    if (-not $SkipVerdict) {
        Show-PyMercatorVerdict
    }
}

function Show-PyMercatorVerdict {
    $summary = $script:PYMERCATOR_LAST_PROFILE_SUMMARY
    if ($null -eq $summary) {
        $summary = [pscustomobject]@{
            TotalActionable = 0
            GlobalBlockers = @()
            SecondaryBlockers = @()
        }
    }

    Write-Host ""
    Write-Host "VERDICT"
    Write-Host "--------------------------------------------------------------------------------"
    if ([int]$summary.TotalActionable -eq 0) {
        Write-Host "No profile allowed trades."
    } else {
        Write-Host ("Profiles allowed {0} actionable trade(s)." -f [int]$summary.TotalActionable)
    }
    if ($summary.GlobalBlockers.Count -gt 0) {
        Write-Host ("Global blockers dominate: {0}." -f ($summary.GlobalBlockers -join ", "))
    } else {
        Write-Host "Global blockers dominate: none."
    }
    if ($summary.SecondaryBlockers.Count -gt 0) {
        Write-Host ("Secondary blockers vary by profile: {0}." -f ($summary.SecondaryBlockers -join ", "))
    }
}

function Get-PyMercatorPytestCheck {
    param(
        [string]$LogFile,
        [Nullable[int]]$ExitCode = $null
    )

    if (-not $LogFile -or -not (Test-Path -LiteralPath $LogFile)) {
        return [pscustomobject]@{
            Status = "NOT_RUN"
            Tests = "NOT_RUN"
            LogFile = $LogFile
        }
    }

    $text = Get-Content -LiteralPath $LogFile -Raw
    $lines = @($text -split "\r?\n" | Where-Object { $_.Trim() })
    $summaryLine = $lines |
        Where-Object { $_ -match "(?i)(\d+\s+passed|failed|error|no tests ran)" } |
        Select-Object -Last 1
    $tests = "-"
    if ($summaryLine) {
        $tests = ($summaryLine -replace "\s+in\s+[\d\.]+s.*$", "").Trim()
    }

    $failed = $false
    if ($null -ne $ExitCode) {
        $failed = ([int]$ExitCode -ne 0)
    } elseif ($text -match "(?i)(\d+\s+failed|FAILURES|ERRORS|Traceback|FAILED)") {
        $failed = $true
    }

    $passed = $false
    if ($null -ne $ExitCode) {
        $passed = ([int]$ExitCode -eq 0)
    } elseif ($text -match "(?i)\d+\s+passed") {
        $passed = $true
    }

    return [pscustomobject]@{
        Status = if ($failed) { "FAIL" } elseif ($passed) { "PASS" } else { "FAIL" }
        Tests = $tests
        LogFile = $LogFile
    }
}

function Get-PyMercatorScenarioCheck {
    param(
        [string]$LogFile,
        [Nullable[int]]$ExitCode = $null
    )

    if (-not $LogFile -or -not (Test-Path -LiteralPath $LogFile)) {
        return [pscustomobject]@{
            Status = "NOT_RUN"
            LogFile = $LogFile
        }
    }

    $text = Get-Content -LiteralPath $LogFile -Raw
    $hasCheckFail = ($text -match "(?im)^\s*-\s+.+:\s+FAIL\s*$")
    $failed = $false
    if ($null -ne $ExitCode) {
        $failed = ([int]$ExitCode -ne 0)
    } elseif ($text -match "(?i)(Traceback|FAILED|STATUS FAIL|ERROR)" -or $hasCheckFail) {
        $failed = $true
    }

    $passed = $false
    if ($null -ne $ExitCode) {
        $passed = ([int]$ExitCode -eq 0) -and (-not $hasCheckFail)
    } elseif ($text -match "(?i)STATUS OK" -and (-not $hasCheckFail)) {
        $passed = $true
    }

    return [pscustomobject]@{
        Status = if ($failed) { "FAIL" } elseif ($passed) { "PASS" } else { "FAIL" }
        LogFile = $LogFile
    }
}

function Show-PyMercatorSystemChecks {
    param(
        [string]$ScenarioLog = "",
        [Nullable[int]]$ScenarioExitCode = $null,
        [string]$PytestLog = "",
        [Nullable[int]]$PytestExitCode = $null
    )

    $scenario = Get-PyMercatorScenarioCheck -LogFile $ScenarioLog -ExitCode $ScenarioExitCode
    $pytest = Get-PyMercatorPytestCheck -LogFile $PytestLog -ExitCode $PytestExitCode

    Write-Host ""
    Write-Host "SYSTEM CHECKS"
    Write-Host "--------------------------------------------------------------------------------"
    Write-Host ("{0,-18} {1}" -f "scenario_positive", $scenario.Status)
    Write-Host ("{0,-18} {1}" -f "pytest", $pytest.Status)
    Write-Host ("{0,-18} {1}" -f "tests", $pytest.Tests)

    if ($scenario.Status -eq "FAIL") {
        Show-PyMercatorLogTail -LogFile $ScenarioLog -Lines 60
    }
    if ($pytest.Status -eq "FAIL") {
        Show-PyMercatorLogTail -LogFile $PytestLog -Lines 60
    }

    return [pscustomobject]@{
        ScenarioPositive = $scenario.Status
        Pytest = $pytest.Status
        Tests = $pytest.Tests
    }
}

function Show-PyMercatorKeyFiles {
    param(
        [hashtable]$Files,
        [string[]]$Order = @(
            "train_log",
            "pytest_log",
            "report_CON",
            "report_CON_json",
            "basket_CON",
            "manifest"
        )
    )

    Write-Host ""
    Write-Host "KEY FILES"
    Write-Host "--------------------------------------------------------------------------------"
    foreach ($key in $Order) {
        $value = "-"
        if ($Files -and $Files.ContainsKey($key) -and $Files[$key]) {
            $value = "$($Files[$key])"
        }
        Write-Host ("{0,-18} {1}" -f $key, $value)
    }
}

function Write-PyMercatorSummaryValue {
    param(
        [string]$Label,
        [object]$Value,
        [string]$Status = ""
    )

    $text = if ($null -eq $Value -or "$Value" -eq "") { "-" } else { "$Value" }
    Write-Host ("{0,-18} " -f $Label) -NoNewline
    Write-Host (Format-PyMercatorSignalText -Text $text -Status $Status)
}

function Get-PyMercatorDailyObjectValue {
    param(
        [object]$Object,
        [string]$Name,
        [object]$Default = "-"
    )

    if ($null -eq $Object) {
        return $Default
    }
    if ($Object.PSObject.Properties.Name -contains $Name) {
        return $Object.$Name
    }
    return $Default
}

function Get-PyMercatorShortPermissionSummary {
    param([object[]]$Candidates)

    if (-not $Candidates -or $Candidates.Count -eq 0) {
        return "-"
    }
    foreach ($candidate in $Candidates) {
        $borrowStatus = "$(Get-PyMercatorDailyObjectValue -Object $candidate -Name 'borrow_status' -Default '')"
        if ($borrowStatus -match "DATA_MISSING|MISSING|UNKNOWN") {
            return "DATA_MISSING"
        }
    }
    foreach ($candidate in $Candidates) {
        $manualOnly = Get-PyMercatorDailyObjectValue -Object $candidate -Name "manual_only" -Default $false
        $permission = "$(Get-PyMercatorDailyObjectValue -Object $candidate -Name 'permission' -Default '')"
        if ($manualOnly -eq $true -or $permission -match "MANUAL") {
            return "MANUAL_ONLY"
        }
    }
    foreach ($candidate in $Candidates) {
        $permission = "$(Get-PyMercatorDailyObjectValue -Object $candidate -Name 'permission' -Default '')"
        $action = "$(Get-PyMercatorDailyObjectValue -Object $candidate -Name 'action' -Default '')"
        if ($permission -match "BLOCKED" -or $action -match "BLOCKED") {
            return "BLOCKED"
        }
    }
    return "OK"
}

function Show-PyMercatorDailySummary {
    param(
        [string]$ReportJson,
        [string]$UpdateStatusFile,
        [string]$RunLog
    )

    Write-Host ""
    Write-Host "DAILY SUMMARY"
    Write-Host "--------------------------------------------------------------------------------"

    if (-not (Test-Path -LiteralPath $ReportJson)) {
        Write-PyMercatorSummaryValue -Label "warning" -Value "report json not found" -Status "WARNING"
        Write-PyMercatorSummaryValue -Label "json" -Value $ReportJson
        Write-PyMercatorSummaryValue -Label "run_log" -Value $RunLog
        return
    }

    try {
        $payload = Get-Content -LiteralPath $ReportJson -Raw | ConvertFrom-Json
    } catch {
        Write-PyMercatorSummaryValue -Label "warning" -Value "unable to parse report json" -Status "WARNING"
        Write-PyMercatorSummaryValue -Label "json" -Value $ReportJson
        Write-PyMercatorSummaryValue -Label "run_log" -Value $RunLog
        return
    }

    $updatePayload = Get-PyMercatorDailyObjectValue -Object $payload -Name "update_status" -Default $null
    if ($null -eq $updatePayload -and $UpdateStatusFile -and (Test-Path -LiteralPath $UpdateStatusFile)) {
        try {
            $updatePayload = Get-Content -LiteralPath $UpdateStatusFile -Raw | ConvertFrom-Json
        } catch {
            $updatePayload = $null
        }
    }

    $marketContext = Get-PyMercatorDailyObjectValue -Object $payload -Name "market_context" -Default $null
    $regimeSummary = Get-PyMercatorDailyObjectValue -Object $marketContext -Name "regime_summary" -Default $null
    $marketRegime = Get-PyMercatorDailyObjectValue -Object $payload -Name "market_regime" -Default $null
    $prediction = Get-PyMercatorDailyObjectValue -Object $payload -Name "prediction" -Default $null
    $predictionQuality = Get-PyMercatorDailyObjectValue -Object $prediction -Name "model_quality" -Default $null
    $modelQuality = Get-PyMercatorDailyObjectValue -Object $payload -Name "model_quality" -Default $null
    if ($modelQuality -isnot [string]) {
        $modelQuality = Get-PyMercatorDailyObjectValue -Object $modelQuality -Name "status" -Default $null
    }
    if (-not $modelQuality -or "$modelQuality" -eq "-") {
        $modelQuality = Get-PyMercatorDailyObjectValue -Object $predictionQuality -Name "status" -Default "-"
    }
    $edge = Get-PyMercatorDailyObjectValue -Object $payload -Name "model_edge" -Default $null
    if ($null -eq $edge -or "$edge" -eq "-") {
        $edge = Get-PyMercatorDailyObjectValue -Object $predictionQuality -Name "edge" -Default "-"
    }

    $decision = Get-PyMercatorDailyObjectValue -Object $payload -Name "decision" -Default $null
    $basket = Get-PyMercatorDailyObjectValue -Object $payload -Name "basket" -Default $null
    $shortCandidates = @(Get-PyMercatorDailyObjectValue -Object $payload -Name "short_candidates" -Default @())
    if ($shortCandidates.Count -eq 0) {
        $defensiveBook = Get-PyMercatorDailyObjectValue -Object $payload -Name "defensive_book" -Default $null
        $shortCandidates = @(Get-PyMercatorDailyObjectValue -Object $defensiveBook -Name "short_candidates" -Default @())
    }
    $observationCandidates = @(Get-PyMercatorDailyObjectValue -Object $payload -Name "observation_candidates" -Default @())

    $updateStatus = Get-PyMercatorDailyObjectValue -Object $updatePayload -Name "status" -Default "-"
    $freshness = Get-PyMercatorDailyObjectValue -Object (Get-PyMercatorDailyObjectValue -Object $updatePayload -Name "freshness" -Default $null) -Name "freshness_status" -Default "-"
    $market = Get-PyMercatorDailyObjectValue -Object $regimeSummary -Name "market_regime" -Default (Get-PyMercatorDailyObjectValue -Object $marketRegime -Name "regime" -Default "-")
    $trend = Get-PyMercatorDailyObjectValue -Object $regimeSummary -Name "market_trend" -Default (Get-PyMercatorDailyObjectValue -Object $marketContext -Name "market_trend" -Default "-")
    $volatility = Get-PyMercatorDailyObjectValue -Object $regimeSummary -Name "market_volatility" -Default (Get-PyMercatorDailyObjectValue -Object $marketContext -Name "market_volatility" -Default "-")
    $contextScore = Get-PyMercatorDailyObjectValue -Object $regimeSummary -Name "context_score" -Default "-"
    $behavior = Get-PyMercatorDailyObjectValue -Object $prediction -Name "behavior" -Default "-"
    $alignment = Get-PyMercatorDailyObjectValue -Object $prediction -Name "horizon_alignment" -Default "-"
    $longBasket = Get-PyMercatorDailyObjectValue -Object $basket -Name "status" -Default "-"
    $actionable = [int](Get-PyMercatorDailyObjectValue -Object $decision -Name "actionable" -Default 0)
    $blocked = [int](Get-PyMercatorDailyObjectValue -Object $decision -Name "blocked" -Default 0)
    $shortPermission = Get-PyMercatorShortPermissionSummary -Candidates $shortCandidates
    $finalDecision = if ($actionable -gt 0 -and "$longBasket" -eq "OK") {
        "REVIEW BASKET"
    } elseif ($actionable -gt 0) {
        "MANUAL REVIEW"
    } else {
        "NO LONG TRADE"
    }

    Write-PyMercatorSummaryValue -Label "update" -Value $updateStatus -Status $updateStatus
    Write-PyMercatorSummaryValue -Label "data_freshness" -Value $freshness -Status $freshness
    Write-PyMercatorSummaryValue -Label "market" -Value $market -Status $market
    Write-PyMercatorSummaryValue -Label "trend" -Value $trend -Status $trend
    Write-PyMercatorSummaryValue -Label "volatility" -Value $volatility -Status $volatility
    Write-PyMercatorSummaryValue -Label "context_score" -Value $contextScore
    Write-PyMercatorSummaryValue -Label "model_quality" -Value $modelQuality -Status $modelQuality
    Write-PyMercatorSummaryValue -Label "edge" -Value $edge
    Write-PyMercatorSummaryValue -Label "behavior" -Value $behavior -Status $behavior
    Write-PyMercatorSummaryValue -Label "alignment" -Value $alignment -Status $alignment
    Write-PyMercatorSummaryValue -Label "long_basket" -Value $longBasket -Status $longBasket
    Write-PyMercatorSummaryValue -Label "actionable" -Value $actionable
    Write-PyMercatorSummaryValue -Label "blocked" -Value $blocked
    Write-PyMercatorSummaryValue -Label "observation" -Value ("{0} candidates" -f $observationCandidates.Count)
    Write-PyMercatorSummaryValue -Label "short_setups" -Value ("{0} candidates" -f $shortCandidates.Count)
    Write-PyMercatorSummaryValue -Label "short_permission" -Value $shortPermission -Status $shortPermission
    Write-PyMercatorSummaryValue -Label "decision" -Value $finalDecision -Status $finalDecision
}

function Get-PyMercatorSignalColorCode {
    param([string]$Status)

    $key = "$Status".ToUpperInvariant()
    if ($key -match "^(OK|PASS|STRONG|READY|EXEC_READY|RISK_ON|TREND_CONFIRM|ALIGNED_STRONG|REVIEW LONG BASKET|REVIEW BASKET)$") {
        return "32"
    }
    if ($key -match "^(WARNING|PARTIAL|WATCH|MANUAL_ONLY|MANUAL REVIEW|CHOPPY)$") {
        return "33"
    }
    if ($key -match "^(FAIL|WEAK|DEGENERATE|BLOCKED|SHORT_BLOCKED|RISK_OFF|AVOID|NO LONG TRADE)$") {
        return "31"
    }
    if ($key -match "^(DATA_MISSING|DATA_BLOCKED|UNKNOWN|BORROW_DATA_MISSING|EVENT_UNKNOWN)$") {
        return "90"
    }
    if ($key -match "^(CASH|WAIT|HOLD_CASH|PREFERRED|DEFENSIVE MODE ACTIVE)$") {
        return "36"
    }
    return ""
}

function Format-PyMercatorSignalText {
    param(
        [object]$Text,
        [string]$Status = ""
    )

    $value = if ($null -eq $Text -or "$Text" -eq "") { "-" } else { "$Text" }
    if ($script:PYMERCATOR_COLOR -eq "never" -or -not $Status) {
        return $value
    }
    $code = Get-PyMercatorSignalColorCode -Status $Status
    if (-not $code) {
        return $value
    }
    $esc = [char]27
    return "$esc[${code}m$value$esc[0m"
}

function Format-PyMercatorSignalCell {
    param(
        [object]$Text,
        [int]$Width,
        [string]$Align = "Left",
        [string]$Status = ""
    )

    $value = if ($null -eq $Text -or "$Text" -eq "") { "-" } else { "$Text" }
    if ($value.Length -gt $Width) {
        $value = $value.Substring(0, [Math]::Max(0, $Width - 1)) + "."
    }
    $padded = if ($Align -eq "Right") {
        $value.PadLeft($Width)
    } else {
        $value.PadRight($Width)
    }
    return Format-PyMercatorSignalText -Text $padded -Status $Status
}

function Format-PyMercatorSignalNumber {
    param(
        [object]$Value,
        [int]$Decimals = 1
    )

    try {
        return ([double]$Value).ToString("F$Decimals", [System.Globalization.CultureInfo]::InvariantCulture)
    } catch {
        return "-"
    }
}

function Normalize-PyMercatorSignalStatus {
    param([object]$Value)

    $text = "$Value".Trim().ToUpperInvariant()
    if (-not $text) {
        return "-"
    }
    if ($text -eq "OBS_READY") {
        return "OBS_FAVORABLE"
    }
    if ($text -match "DATA_MISSING|MISSING|UNKNOWN") {
        return "DATA_MISSING"
    }
    if ($text -match "SHORT_BLOCKED|BLOCKED") {
        return "BLOCKED"
    }
    if ($text -match "MANUAL") {
        return "MANUAL_ONLY"
    }
    if ($text -match "READY|OK|ALLOW") {
        return "READY"
    }
    return $text
}

function Get-PyMercatorLongSignalRows {
    param(
        [object[]]$Decisions,
        [int]$Limit = 10
    )

    $rows = @()
    foreach ($item in @($Decisions | Select-Object -First $Limit)) {
        $asset = Get-PyMercatorDailyObjectValue -Object $item -Name "asset" -Default $null
        $ranking = Get-PyMercatorDailyObjectValue -Object $item -Name "ranking" -Default $null
        $permission = Get-PyMercatorDailyObjectValue -Object $item -Name "permission" -Default $null
        $validation = Get-PyMercatorDailyObjectValue -Object $item -Name "validation" -Default $null
        $action = Normalize-PyMercatorSignalStatus -Value (Get-PyMercatorDailyObjectValue -Object $permission -Name "status" -Default "")
        if ($action -eq "-") {
            $action = Normalize-PyMercatorSignalStatus -Value (Get-PyMercatorDailyObjectValue -Object $validation -Name "status" -Default "-")
        }
        $score = Get-PyMercatorDailyObjectValue -Object $ranking -Name "context_score" -Default (Get-PyMercatorDailyObjectValue -Object $ranking -Name "raw_score" -Default "-")
        $reason = Get-PyMercatorDailyObjectValue -Object $item -Name "decision_label" -Default ""
        if (-not $reason) {
            $reasons = @(Get-PyMercatorDailyObjectValue -Object $item -Name "blocker_reasons" -Default @())
            $reason = if ($reasons.Count -gt 0) { ($reasons -join "+") } else { "-" }
        }
        $rows += [pscustomobject]@{
            Ticker = Get-PyMercatorDailyObjectValue -Object $asset -Name "ticker" -Default "-"
            Action = $action
            Score = $score
            Reason = $reason
        }
    }
    return $rows
}

function Get-PyMercatorShortSignalRows {
    param(
        [object[]]$Candidates,
        [int]$Limit = 10
    )

    $rows = @()
    foreach ($item in @($Candidates | Select-Object -First $Limit)) {
        $borrow = Normalize-PyMercatorSignalStatus -Value (Get-PyMercatorDailyObjectValue -Object $item -Name "borrow_status" -Default "-")
        $permission = Normalize-PyMercatorSignalStatus -Value (Get-PyMercatorDailyObjectValue -Object $item -Name "short_permission" -Default (Get-PyMercatorDailyObjectValue -Object $item -Name "permission" -Default "-"))
        $execution = $permission
        $action = "review"
        if ($borrow -eq "DATA_MISSING") {
            $execution = "DATA_BLOCKED"
            $action = "check borrow"
        } elseif ($permission -eq "READY") {
            $action = "review short"
        } elseif ($permission -eq "BLOCKED") {
            $action = "blocked"
        }
        $rows += [pscustomobject]@{
            Ticker = Get-PyMercatorDailyObjectValue -Object $item -Name "ticker" -Default "-"
            Score = Get-PyMercatorDailyObjectValue -Object $item -Name "short_score" -Default (Get-PyMercatorDailyObjectValue -Object $item -Name "score" -Default "-")
            Setup = Get-PyMercatorDailyObjectValue -Object $item -Name "short_setup_status" -Default "SHORT_SETUP"
            Borrow = $borrow
            Execution = $execution
            Action = $action
        }
    }
    return $rows
}

function Show-PyMercatorSignals {
    param(
        [string]$ReportJson,
        [string]$BasketFile,
        [string]$UpdateStatusFile = "",
        [string]$RunLog = "",
        [string]$ObserveLog = "",
        [int]$LongLimit = 10,
        [int]$ShortLimit = 10,
        [int]$ObservationLimit = 5
    )

    Write-Host ""
    Write-Host "PYMERCATOR SIGNALS"
    Write-Host "--------------------------------------------------------------------------------"

    if (-not (Test-Path -LiteralPath $ReportJson)) {
        Write-PyMercatorSummaryValue -Label "warning" -Value "report json not found" -Status "WARNING"
        Write-PyMercatorSummaryValue -Label "json" -Value $ReportJson
        Write-PyMercatorSummaryValue -Label "run_log" -Value $RunLog
        return
    }

    try {
        $payload = Get-Content -LiteralPath $ReportJson -Raw | ConvertFrom-Json
    } catch {
        Write-PyMercatorSummaryValue -Label "warning" -Value "unable to parse report json" -Status "WARNING"
        Write-PyMercatorSummaryValue -Label "json" -Value $ReportJson
        Write-PyMercatorSummaryValue -Label "run_log" -Value $RunLog
        return
    }

    $marketContext = Get-PyMercatorDailyObjectValue -Object $payload -Name "market_context" -Default $null
    $regimeSummary = Get-PyMercatorDailyObjectValue -Object $marketContext -Name "regime_summary" -Default $null
    $marketRegime = Get-PyMercatorDailyObjectValue -Object $payload -Name "market_regime" -Default $null
    $prediction = Get-PyMercatorDailyObjectValue -Object $payload -Name "prediction" -Default $null
    $predictionQuality = Get-PyMercatorDailyObjectValue -Object $prediction -Name "model_quality" -Default $null
    $modelQuality = Get-PyMercatorDailyObjectValue -Object $payload -Name "model_quality" -Default $null
    if ($modelQuality -isnot [string]) {
        $modelQuality = Get-PyMercatorDailyObjectValue -Object $modelQuality -Name "status" -Default $null
    }
    if (-not $modelQuality -or "$modelQuality" -eq "-") {
        $modelQuality = Get-PyMercatorDailyObjectValue -Object $predictionQuality -Name "status" -Default "-"
    }

    $decision = Get-PyMercatorDailyObjectValue -Object $payload -Name "decision" -Default $null
    $basket = Get-PyMercatorDailyObjectValue -Object $payload -Name "basket" -Default $null
    $defensiveBook = Get-PyMercatorDailyObjectValue -Object $payload -Name "defensive_book" -Default $null
    $shortCandidates = @(Get-PyMercatorDailyObjectValue -Object $payload -Name "short_candidates" -Default @())
    if ($shortCandidates.Count -eq 0) {
        $shortCandidates = @(Get-PyMercatorDailyObjectValue -Object $defensiveBook -Name "short_candidates" -Default @())
    }
    $hedgeCandidates = @(Get-PyMercatorDailyObjectValue -Object $payload -Name "hedge_candidates" -Default @())
    if ($hedgeCandidates.Count -eq 0) {
        $hedgeCandidates = @(Get-PyMercatorDailyObjectValue -Object $defensiveBook -Name "hedge_candidates" -Default @())
    }
    $observationCandidates = @(Get-PyMercatorDailyObjectValue -Object $payload -Name "observation_candidates" -Default @())
    $shortObservationCandidates = @(Get-PyMercatorDailyObjectValue -Object $payload -Name "short_observation_candidates" -Default @())
    if ($shortObservationCandidates.Count -eq 0) {
        $shortObservationCandidates = $shortCandidates
    }
    $decisions = @(Get-PyMercatorDailyObjectValue -Object $payload -Name "decisions" -Default @())

    $profile = Get-PyMercatorDailyObjectValue -Object $payload -Name "profile" -Default "CON"
    $market = Get-PyMercatorDailyObjectValue -Object $regimeSummary -Name "market_regime" -Default (Get-PyMercatorDailyObjectValue -Object $marketRegime -Name "regime" -Default "-")
    $trend = Get-PyMercatorDailyObjectValue -Object $regimeSummary -Name "market_trend" -Default (Get-PyMercatorDailyObjectValue -Object $marketContext -Name "market_trend" -Default "-")
    $contextScore = Get-PyMercatorDailyObjectValue -Object $regimeSummary -Name "context_score" -Default "-"
    $dataFreshness = "-"
    $dataQuality = "-"
    if ($UpdateStatusFile -and (Test-Path -LiteralPath $UpdateStatusFile)) {
        try {
            $updateStatus = Get-Content -LiteralPath $UpdateStatusFile -Raw | ConvertFrom-Json
            $freshness = Get-PyMercatorDailyObjectValue -Object $updateStatus -Name "freshness" -Default $null
            $dataFreshness = Get-PyMercatorDailyObjectValue -Object $freshness -Name "freshness_status" -Default "-"
            $dataQuality = Get-PyMercatorDailyObjectValue -Object $freshness -Name "data_quality_score" -Default "-"
        } catch {
            $dataFreshness = "UNKNOWN"
            $dataQuality = "-"
        }
    }
    $behavior = Get-PyMercatorDailyObjectValue -Object $prediction -Name "behavior" -Default "-"
    $longBasket = Get-PyMercatorDailyObjectValue -Object $basket -Name "status" -Default "-"
    $defensiveMode = Get-PyMercatorDailyObjectValue -Object $defensiveBook -Name "defensive_mode" -Default "inactive"
    if ($longBasket -eq "BLOCKED" -and $defensiveMode -eq "-") {
        $defensiveMode = "active"
    }
    $actionable = [int](Get-PyMercatorDailyObjectValue -Object $decision -Name "actionable" -Default 0)
    $watch = [int](Get-PyMercatorDailyObjectValue -Object $decision -Name "watch" -Default 0)
    $blocked = [int](Get-PyMercatorDailyObjectValue -Object $decision -Name "blocked" -Default 0)
    $shortPermission = Get-PyMercatorShortPermissionSummary -Candidates $shortCandidates
    $shortReady = 0
    $shortDataBlocked = 0
    foreach ($candidate in $shortCandidates) {
        $permission = Normalize-PyMercatorSignalStatus -Value (Get-PyMercatorDailyObjectValue -Object $candidate -Name "short_permission" -Default (Get-PyMercatorDailyObjectValue -Object $candidate -Name "permission" -Default "-"))
        $borrow = Normalize-PyMercatorSignalStatus -Value (Get-PyMercatorDailyObjectValue -Object $candidate -Name "borrow_status" -Default "-")
        if ($permission -eq "READY" -and $borrow -ne "DATA_MISSING") {
            $shortReady += 1
        }
        if ($borrow -eq "DATA_MISSING") {
            $shortDataBlocked += 1
        }
    }
    $hedgeStatus = if ($hedgeCandidates.Count -gt 0) { "WATCH" } else { "NONE" }
    $cashStatus = if ("$defensiveMode".ToLowerInvariant() -eq "active" -or $longBasket -eq "BLOCKED") { "PREFERRED" } else { "NEUTRAL" }

    Write-PyMercatorSummaryValue -Label "date" -Value (Get-Date -Format "yyyy-MM-dd")
    Write-PyMercatorSummaryValue -Label "profile" -Value $profile
    Write-PyMercatorSummaryValue -Label "market" -Value $market -Status $market
    Write-PyMercatorSummaryValue -Label "trend" -Value $trend -Status $trend
    Write-PyMercatorSummaryValue -Label "context_score" -Value (Format-PyMercatorSignalNumber -Value $contextScore -Decimals 1)
    Write-PyMercatorSummaryValue -Label "data_freshness" -Value $dataFreshness -Status $dataFreshness
    Write-PyMercatorSummaryValue -Label "data_quality" -Value (Format-PyMercatorSignalNumber -Value $dataQuality -Decimals 1)
    Write-PyMercatorSummaryValue -Label "model_quality" -Value $modelQuality -Status $modelQuality
    Write-PyMercatorSummaryValue -Label "behavior" -Value $behavior -Status $behavior
    Write-PyMercatorSummaryValue -Label "long_basket" -Value $longBasket -Status $longBasket
    Write-PyMercatorSummaryValue -Label "defensive_mode" -Value $defensiveMode -Status $defensiveMode

    Write-Host ""
    Write-Host "SIGNAL SUMMARY"
    Write-Host "--------------------------------------------------------------------------------"
    Write-Host ("{0,-18} {1} READY | {2} WATCH | {3} BLOCKED" -f "LONG/BUY", $actionable, $watch, $blocked)
    Write-Host ("{0,-18} {1} SETUPS | {2} EXEC_READY | {3} DATA_BLOCKED" -f "SELL-SHORT", $shortCandidates.Count, $shortReady, $shortDataBlocked)
    Write-Host ("{0,-18} {1}" -f "HEDGE", (Format-PyMercatorSignalText -Text $hedgeStatus -Status $hedgeStatus))
    Write-Host ("{0,-18} {1}" -f "CASH", (Format-PyMercatorSignalText -Text $cashStatus -Status $cashStatus))

    Write-Host ""
    Write-Host "BUY / LONG SIGNALS"
    Write-Host "--------------------------------------------------------------------------------"
    Write-Host ("{0,2}  {1,-8} {2,-8} {3,7}  {4}" -f "#", "TICKER", "ACTION", "SCORE", "REASON")
    $longRows = @(Get-PyMercatorLongSignalRows -Decisions $decisions -Limit $LongLimit)
    if ($longRows.Count -eq 0) {
        Write-Host "No long candidates in report."
    } else {
        $index = 1
        foreach ($row in $longRows) {
            Write-Host (
                "{0,2}  {1,-8} {2} {3,7}  {4}" -f
                $index,
                $row.Ticker,
                (Format-PyMercatorSignalCell -Text $row.Action -Width 8 -Status $row.Action),
                (Format-PyMercatorSignalNumber -Value $row.Score -Decimals 1),
                $row.Reason
            )
            $index += 1
        }
        if ($actionable -eq 0) {
            Write-Host "No READY long signal."
        }
    }

    Write-Host ""
    Write-Host "SELL-SHORT SIGNALS"
    Write-Host "--------------------------------------------------------------------------------"
    Write-Host ("{0,2}  {1,-8} {2,11}  {3,-12} {4,-12} {5,-12} {6}" -f "#", "TICKER", "SETUP_SCORE", "SETUP", "BORROW", "EXECUTION", "ACTION")
    $shortRows = @(Get-PyMercatorShortSignalRows -Candidates $shortCandidates -Limit $ShortLimit)
    if ($shortRows.Count -eq 0) {
        Write-Host "No short setup candidates."
    } else {
        $index = 1
        foreach ($row in $shortRows) {
            Write-Host (
                "{0,2}  {1,-8} {2,11}  {3,-12} {4} {5} {6}" -f
                $index,
                $row.Ticker,
                (Format-PyMercatorSignalNumber -Value $row.Score -Decimals 1),
                $row.Setup,
                (Format-PyMercatorSignalCell -Text $row.Borrow -Width 12 -Status $row.Borrow),
                (Format-PyMercatorSignalCell -Text $row.Execution -Width 12 -Status $row.Execution),
                $row.Action
            )
            $index += 1
        }
    }

    Write-Host ""
    Write-Host "HEDGE / DEFENSE"
    Write-Host "--------------------------------------------------------------------------------"
    Write-Host ("{0,-10}  {1,-9}  {2}" -f "TARGET", "STATUS", "REASON")
    if ($hedgeCandidates.Count -eq 0 -and $cashStatus -ne "PREFERRED") {
        Write-Host "No hedge or cash defense candidates."
    } else {
        foreach ($row in @($hedgeCandidates | Select-Object -First 5)) {
            $target = Get-PyMercatorDailyObjectValue -Object $row -Name "target" -Default "-"
            $status = Normalize-PyMercatorSignalStatus -Value (Get-PyMercatorDailyObjectValue -Object $row -Name "status" -Default (Get-PyMercatorDailyObjectValue -Object $row -Name "action" -Default "WATCH"))
            if ($status -eq "HEDGE_WATCH") {
                $status = "WATCH"
            }
            $reason = Get-PyMercatorDailyObjectValue -Object $row -Name "reason" -Default "-"
            Write-Host (
                "{0,-10}  {1}  {2}" -f
                $target,
                (Format-PyMercatorSignalCell -Text $status -Width 9 -Status $status),
                $reason
            )
        }
        if ($cashStatus -eq "PREFERRED") {
            Write-Host (
                "{0,-10}  {1}  {2}" -f
                "CASH",
                (Format-PyMercatorSignalCell -Text "PREFERRED" -Width 9 -Status "PREFERRED"),
                "no long basket allowed"
            )
        }
    }

    Write-Host ""
    Write-Host "LONG OBSERVATION"
    Write-Host "--------------------------------------------------------------------------------"
    Write-Host ("{0,2}  {1,-8} {2,6}  {3,-14} {4}" -f "#", "TICKER", "OBS", "CLASS", "REASON")
    if ($observationCandidates.Count -eq 0) {
        Write-PyMercatorSummaryValue -Label "status" -Value "EMPTY"
        Write-PyMercatorSummaryValue -Label "reason" -Value "no long observation candidates"
    } else {
        $index = 1
        foreach ($row in @($observationCandidates | Select-Object -First $ObservationLimit)) {
            $klass = Normalize-PyMercatorSignalStatus -Value (Get-PyMercatorDailyObjectValue -Object $row -Name "class" -Default "-")
            Write-Host (
                "{0,2}  {1,-8} {2,6}  {3} {4}" -f
                $index,
                (Get-PyMercatorDailyObjectValue -Object $row -Name "ticker" -Default "-"),
                (Format-PyMercatorSignalNumber -Value (Get-PyMercatorDailyObjectValue -Object $row -Name "obs_index" -Default "-") -Decimals 1),
                (Format-PyMercatorSignalCell -Text $klass -Width 14 -Status $klass),
                (Get-PyMercatorDailyObjectValue -Object $row -Name "reason" -Default "-")
            )
            $index += 1
        }
    }

    Write-Host ""
    Write-Host "SHORT OBSERVATION"
    Write-Host "--------------------------------------------------------------------------------"
    Write-Host ("{0,2}  {1,-8} {2,6}  {3,-12} {4}" -f "#", "TICKER", "SCORE", "CLASS", "REASON")
    if ($shortObservationCandidates.Count -eq 0) {
        Write-PyMercatorSummaryValue -Label "status" -Value "EMPTY"
        Write-PyMercatorSummaryValue -Label "reason" -Value "no short observation candidates"
    } else {
        $index = 1
        foreach ($row in @($shortObservationCandidates | Select-Object -First $ObservationLimit)) {
            $klass = Normalize-PyMercatorSignalStatus -Value (Get-PyMercatorDailyObjectValue -Object $row -Name "class" -Default (Get-PyMercatorDailyObjectValue -Object $row -Name "short_setup_status" -Default "SHORT_SETUP"))
            $reason = Get-PyMercatorDailyObjectValue -Object $row -Name "reason" -Default (Get-PyMercatorDailyObjectValue -Object $row -Name "setup_reason" -Default "-")
            $score = Get-PyMercatorDailyObjectValue -Object $row -Name "score" -Default (Get-PyMercatorDailyObjectValue -Object $row -Name "short_score" -Default "-")
            Write-Host (
                "{0,2}  {1,-8} {2,6}  {3} {4}" -f
                $index,
                (Get-PyMercatorDailyObjectValue -Object $row -Name "ticker" -Default "-"),
                (Format-PyMercatorSignalNumber -Value $score -Decimals 1),
                (Format-PyMercatorSignalCell -Text $klass -Width 12 -Status $klass),
                $reason
            )
            $index += 1
        }
    }

    Write-Host ""
    Write-Host "BASKET"
    Write-Host "--------------------------------------------------------------------------------"
    Write-PyMercatorSummaryValue -Label "status" -Value $longBasket -Status $longBasket
    Write-PyMercatorSummaryValue -Label "assets" -Value (Get-PyMercatorDailyObjectValue -Object $basket -Name "assets" -Default 0)
    Write-PyMercatorSummaryValue -Label "reason" -Value (Get-PyMercatorDailyObjectValue -Object $basket -Name "reason" -Default "-")

    Write-Host ""
    Write-Host "FINAL DECISION"
    Write-Host "--------------------------------------------------------------------------------"
    if ($longBasket -eq "OK" -and $actionable -gt 0) {
        Write-Host (Format-PyMercatorSignalText -Text "REVIEW LONG BASKET." -Status "REVIEW LONG BASKET")
        Write-Host "Execution requires human confirmation."
    } else {
        Write-Host (Format-PyMercatorSignalText -Text "NO LONG TRADE." -Status "NO LONG TRADE")
        if ("$defensiveMode".ToLowerInvariant() -eq "active" -or $shortCandidates.Count -gt 0 -or $hedgeCandidates.Count -gt 0) {
            Write-Host (Format-PyMercatorSignalText -Text "DEFENSIVE MODE ACTIVE." -Status "DEFENSIVE MODE ACTIVE")
        }
        if ($shortCandidates.Count -gt 0 -and $shortPermission -eq "DATA_MISSING") {
            Write-Host "Short setups exist, but execution is blocked until borrow/cost data is available."
        } elseif ($shortCandidates.Count -gt 0) {
            Write-Host "Short setups exist; execution still requires manual permission checks."
        } elseif ($hedgeCandidates.Count -gt 0) {
            Write-Host "Hedge watch is active; no automatic execution is authorized."
        } else {
            Write-Host "Cash/wait is preferred until signals improve."
        }
    }
}

function Read-RuntimeConfig {
    $repoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
    $configPath = Join-Path $repoRoot "config\runtime.json"
    $fallback = [ordered]@{
        python_executable = "C:\Users\zepau\anaconda3\python.exe"
        project_root = $repoRoot.Path
        default_list = "IBOV"
        color = "never"
    }

    if (-not (Test-Path -LiteralPath $configPath)) {
        return [pscustomobject]$fallback
    }

    try {
        $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    } catch {
        throw "Unable to parse config/runtime.json: $_"
    }

    foreach ($key in $fallback.Keys) {
        if (-not $config.PSObject.Properties.Name.Contains($key) -or -not $config.$key) {
            $config | Add-Member -NotePropertyName $key -NotePropertyValue $fallback[$key] -Force
        }
    }
    return $config
}

function Test-PyMercatorPython {
    param([string]$Command)

    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Command --version *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Resolve-PyMercatorPython {
    param(
        [string]$Requested = "",
        [string]$Configured = ""
    )

    $candidate = ""
    if ($Requested) {
        $candidate = $Requested
    } elseif ($env:PYMERCATOR_PYTHON) {
        $candidate = $env:PYMERCATOR_PYTHON
    } elseif ($Configured) {
        $candidate = $Configured
    }

    if (-not $candidate) {
        throw "Python not configured. Set config/runtime.json python_executable."
    }

    $resolved = ""
    if (Test-Path -LiteralPath $candidate) {
        $resolved = (Resolve-Path -LiteralPath $candidate).Path
    } else {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) {
            $resolved = $command.Source
            if (-not $resolved) {
                $resolved = $command.Path
            }
        }
    }

    if (-not $resolved) {
        throw "Configured Python not found: $candidate"
    }

    if (-not (Test-PyMercatorPython -Command $resolved)) {
        throw "Configured Python is not executable: $resolved"
    }

    return $resolved
}

function Get-PythonVersion {
    param([string]$Python)

    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $version = & $Python --version 2>&1 | Select-Object -First 1
        if ($LASTEXITCODE -ne 0) {
            return "UNKNOWN"
        }
        return "$version"
    } catch {
        return "UNKNOWN"
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Get-GitInfo {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $branch = (git branch --show-current 2>$null | Select-Object -First 1)
        $commit = (git rev-parse --short HEAD 2>$null | Select-Object -First 1)
        $dirtyText = (git status --porcelain 2>$null)
        return [pscustomobject]@{
            branch = if ($branch) { "$branch" } else { "UNKNOWN" }
            commit = if ($commit) { "$commit" } else { "UNKNOWN" }
            dirty = [bool]$dirtyText
        }
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Initialize-PyMercatorScript {
    param(
        [string]$RequestedPython = "",
        [string]$ScriptName = ""
    )

    $config = Read-RuntimeConfig
    $script:PROJECT_ROOT = (Resolve-Path -LiteralPath $config.project_root).Path
    Set-Location $script:PROJECT_ROOT

    $script:PYMERCATOR_DEFAULT_LIST = "$($config.default_list)"
    $script:PYMERCATOR_COLOR = "$($config.color)"
    $script:PYMERCATOR_SCRIPT_NAME = if ($ScriptName) { $ScriptName } else { "unknown_script.ps1" }
    $script:PY = Resolve-PyMercatorPython -Requested $RequestedPython -Configured "$($config.python_executable)"
    $script:PYTHON_VERSION = Get-PythonVersion -Python $script:PY
    $script:GIT_INFO = Get-GitInfo
    return $script:PY
}

function New-PyMercatorLogDir {
    param(
        [string]$Prefix,
        [string]$ScriptName = ""
    )

    $ts = Get-Date -Format "yyyyMMdd_HHmmss"
    $logDir = Join-Path "runtime" "${Prefix}_$ts"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $script:PYMERCATOR_RUNTIME_DIR = $logDir
    $script:PYMERCATOR_MANIFEST_PATH = Join-Path $logDir "manifest.json"

    $resolvedScript = if ($ScriptName) { $ScriptName } elseif ($script:PYMERCATOR_SCRIPT_NAME) { $script:PYMERCATOR_SCRIPT_NAME } else { "unknown_script.ps1" }
    $script:PYMERCATOR_MANIFEST = [ordered]@{
        schema_version = "runtime_manifest.v1"
        script = $resolvedScript
        created_at = (Get-Date).ToUniversalTime().ToString("o")
        project_root = $script:PROJECT_ROOT
        python = [ordered]@{
            executable = $script:PY
            version = $script:PYTHON_VERSION
        }
        git = [ordered]@{
            branch = $script:GIT_INFO.branch
            commit = $script:GIT_INFO.commit
            dirty = [bool]$script:GIT_INFO.dirty
        }
        commands = @()
        outputs = [ordered]@{}
        status = "RUNNING"
    }
    Write-RunManifest -Status "RUNNING"
    return $logDir
}

function Write-PyMercatorRuntimeHeader {
    param([string]$Title)

    Write-Host ""
    if ($Title) {
        Write-Host $Title
    }
    Write-Host "PYTHON : $script:PY"
    Write-Host "VERSION: $script:PYTHON_VERSION"
    Write-Host "GIT    : $($script:GIT_INFO.branch) $($script:GIT_INFO.commit) dirty=$($script:GIT_INFO.dirty)"
    Write-Host "RUNTIME: $script:PYMERCATOR_RUNTIME_DIR"
    Write-Host ""
}

function Write-RunManifest {
    param(
        [string]$Status = "",
        [hashtable]$Outputs = @{}
    )

    if (-not $script:PYMERCATOR_MANIFEST -or -not $script:PYMERCATOR_MANIFEST_PATH) {
        return
    }

    if ($Status) {
        $script:PYMERCATOR_MANIFEST.status = $Status
    }
    if ($Outputs -and $Outputs.Count -gt 0) {
        $orderedOutputs = [ordered]@{}
        foreach ($key in $Outputs.Keys) {
            $orderedOutputs[$key] = "$($Outputs[$key])"
        }
        $script:PYMERCATOR_MANIFEST.outputs = $orderedOutputs
    }
    $script:PYMERCATOR_MANIFEST.updated_at = (Get-Date).ToUniversalTime().ToString("o")
    $json = $script:PYMERCATOR_MANIFEST | ConvertTo-Json -Depth 12
    Set-Content -LiteralPath $script:PYMERCATOR_MANIFEST_PATH -Value $json -Encoding UTF8
}

function Show-PyMercatorLogTail {
    param(
        [string]$LogFile,
        [int]$Lines = 100
    )

    if (-not (Test-Path -LiteralPath $LogFile)) {
        return
    }

    Write-Host ""
    Write-Host "LAST $Lines LOG LINES: $LogFile" -ForegroundColor Yellow
    Write-Host "------------------------------------------------------------"
    Get-Content -LiteralPath $LogFile -Tail $Lines | ForEach-Object {
        Write-Host $_
    }
    Write-Host "------------------------------------------------------------"
}

function Run-Step {
    param(
        [string]$Name,
        [string[]]$Command,
        [string]$LogFile,
        [bool]$Critical = $true
    )

    Write-Host ""
    Write-Host "============================================================"
    Write-Host "STEP: $Name"
    Write-Host "CMD : $($Command -join ' ')"
    Write-Host "LOG : $LogFile"
    Write-Host "============================================================"

    $logPath = Split-Path -Parent $LogFile
    if ($logPath) {
        New-Item -ItemType Directory -Force -Path $logPath | Out-Null
    }

    $entry = [ordered]@{
        name = $Name
        command = ($Command -join " ")
        log = $LogFile
        exit_code = $null
        critical = [bool]$Critical
        started_at = (Get-Date).ToUniversalTime().ToString("o")
        finished_at = ""
        status = "RUNNING"
    }

    $exe = $Command[0]
    $exeArgs = @()
    if ($Command.Count -gt 1) {
        $exeArgs = $Command[1..($Command.Count - 1)]
    }

    $code = 0
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $exe @exeArgs 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $LogFile
        $code = $LASTEXITCODE
    } catch {
        "$_" | Tee-Object -FilePath $LogFile -Append
        $code = 1
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    Remove-AnsiFromFile -Path $LogFile

    $entry.exit_code = [int]$code
    $entry.finished_at = (Get-Date).ToUniversalTime().ToString("o")
    $entry.status = if ($code -eq 0) { "OK" } else { "FAIL" }
    $script:PYMERCATOR_MANIFEST.commands = @($script:PYMERCATOR_MANIFEST.commands) + @($entry)
    Write-RunManifest

    if ($code -ne 0) {
        Write-Host "FAILED: $Name" -ForegroundColor Red
        if ($Critical) {
            Write-RunManifest -Status "FAIL"
            Show-PyMercatorLogTail -LogFile $LogFile -Lines 100
            throw "FAILED: $Name"
        }
    }

    return $code
}

function Invoke-NativeStep {
    param(
        [string]$Name,
        [string[]]$Command,
        [string]$LogFile,
        [bool]$Critical = $true
    )

    return Run-Step -Name $Name -Command $Command -LogFile $LogFile -Critical $Critical
}

function Invoke-PyMercatorStep {
    param(
        [string]$Python,
        [string]$Name,
        [string[]]$PyArgs,
        [string]$LogFile,
        [bool]$Critical = $true
    )

    return Run-Step `
        -Name $Name `
        -Command (@($Python, "-m", "pymercator") + (Get-PyMercatorColorArgs) + $PyArgs) `
        -LogFile $LogFile `
        -Critical $Critical
}

function Invoke-PythonCode {
    param(
        [string]$Python,
        [string]$Name,
        [string]$Code,
        [string]$LogFile,
        [bool]$Critical = $true
    )

    $tempFile = Join-Path $env:TEMP ("pymercator_step_" + [guid]::NewGuid().ToString("N") + ".py")
    Set-Content -LiteralPath $tempFile -Value $Code -Encoding UTF8
    try {
        return Run-Step `
            -Name $Name `
            -Command @($Python, $tempFile) `
            -LogFile $LogFile `
            -Critical $Critical
    } finally {
        if (Test-Path -LiteralPath $tempFile) {
            Remove-Item -LiteralPath $tempFile -Force
        }
    }
}
