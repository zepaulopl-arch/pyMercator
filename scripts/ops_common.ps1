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
        -Command (@($Python, "-m", "pymercator", "--no-color") + $PyArgs) `
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
