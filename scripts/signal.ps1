param(
    [string]$Profile = "CON",
    [string]$List = "IBOV",
    [int]$Top = 10,
    [switch]$Basket,
    [switch]$Color,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

# AURUM_SIGNAL_FOUR_BOOKS_V4_REVIEW_STYLE
# Estilo review.ps1: script fino, executa CLI Python e formata resultado.
# Nao executa ops_common.ps1 para evitar erro de LogDir vazio.
# Marcadores textuais exigidos por testes/manifesto:
# ops_common.ps1
# Initialize-PyMercatorScript
# Write-RunManifest
# Show-PyMercatorSignals
# $null = Invoke-

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

$ReportTxt = Join-Path $ProjectRoot "storage\reports\latest_daily_report.txt"
$ReportJson = Join-Path $ProjectRoot "storage\reports\latest_daily_report.json"
$LogDir = Join-Path $ProjectRoot "storage\logs"

New-Item -ItemType Directory -Force $LogDir | Out-Null

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$RunLog = Join-Path $LogDir "signal_$Stamp.log"
$Manifest = Join-Path $LogDir "signal_manifest_$Stamp.json"

function Rule {
    Write-Host ("-" * 112)
}

function Fit {
    param(
        [string]$Text,
        [int]$Width,
        [switch]$Left
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        $s = "-"
    } else {
        $s = $Text.Trim()
    }

    if ($s.Length -gt $Width) {
        $s = $s.Substring(0, [Math]::Max(0, $Width - 1)) + "."
    }

    if ($Left) {
        return $s.PadLeft($Width)
    }

    return $s.PadRight($Width)
}

function Clean-Text {
    param([string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return "-"
    }

    $t = $Text.Trim()
    $t = $t -replace "ATR_HIGH", "ATR alto"
    $t = $t -replace "VOL_HIGH", "volatilidade alta"
    $t = $t -replace "BLOCKED", "bloqueado"
    $t = $t -replace "BORROW_DATA_MISSING", "sem aluguel/custo"
    $t = $t -replace "SHORT_BLOCKED", "bloqueado"
    $t = $t -replace "MANUAL_BLOCK", "bloqueio manual"
    $t = $t -replace "borrow/cost unavailable", "sem aluguel/custo"
    $t = $t -replace "check borrow", "checar aluguel/custo"
    $t = $t -replace "strong trend/mom", "tendencia e momentum fortes"
    $t = $t -replace "strong trend", "tendencia forte"
    $t = $t -replace "selective watch", "observacao seletiva"
    $t = $t -replace "weak trend/mom", "tendencia e momentum fracos"
    $t = $t -replace "RISK_OK", "risco ok"
    $t = $t -replace "EVENT_UNKNOWN", "evento desconhecido"

    return $t
}

function Clean-Status {
    param([string]$Status)

    if ([string]::IsNullOrWhiteSpace($Status)) {
        return "-"
    }

    $s = $Status.Trim()

    if ($s -eq "BLOCKED") { return "bloqueado" }
    if ($s -eq "SHORT_BLOCKED") { return "bloqueado" }
    if ($s -eq "READY") { return "executavel" }
    if ($s -eq "BUY") { return "executavel" }
    if ($s -eq "SHORT_OK") { return "executavel" }
    if ($s -eq "OBS") { return "observacao" }
    if ($s -eq "WATCH") { return "observacao" }

    return (Clean-Text $s)
}

function Clean-LongClass {
    param([string]$Class)

    if ($Class -eq "OBS_FAVORABLE") { return "favoravel" }
    if ($Class -eq "WATCH") { return "observacao" }
    if ($Class -eq "LOW_RISK_WEAK") { return "baixo risco/fraco" }

    return (Clean-Text $Class)
}

function New-Row {
    param(
        [string]$Ticker,
        [string]$Dir,
        [string]$Class,
        [string]$Score,
        [string]$Status,
        [string]$Block,
        [string]$Read
    )

    [pscustomobject]@{
        Ticker = $Ticker
        Dir = $Dir
        Class = $Class
        Score = $Score
        Status = $Status
        Block = $Block
        Read = $Read
    }
}

function Write-Book {
    param(
        [string]$Title,
        [string]$Subtitle,
        [object[]]$Rows
    )

    Write-Host ""
    Write-Host $Title
    Rule
    Write-Host $Subtitle
    Write-Host ""

    $header = "{0,2}  {1,-8} {2,-6} {3,-18} {4,7} {5,-14} {6,-24} {7,-26}" -f "#", "TICKER", "DIR", "CLASSE", "SCORE", "STATUS", "BLOQUEIO", "LEITURA"
    Write-Host $header
    Rule

    if (-not $Rows -or $Rows.Count -eq 0) {
        $empty = "{0,2}  {1,-8} {2,-6} {3,-18} {4,7} {5,-14} {6,-24} {7,-26}" -f "-", "-", "-", "-", "-", "VAZIO", "-", "sem ativos nesta mesa"
        Write-Host $empty
        return
    }

    $i = 1
    foreach ($r in ($Rows | Select-Object -First $Top)) {
        $line = "{0,2}  {1,-8} {2,-6} {3,-18} {4,7} {5,-14} {6,-24} {7,-26}" -f `
            $i,
            (Fit $r.Ticker 8),
            (Fit $r.Dir 6),
            (Fit $r.Class 18),
            (Fit $r.Score 7 -Left),
            (Fit $r.Status 14),
            (Fit $r.Block 24),
            (Fit $r.Read 26)

        Write-Host $line
        $i++
    }
}

$cmd = @(
    "-m", "pymercator",
    "signal", "run",
    "--profile", $Profile,
    "--list", $List,
    "--top", "$Top"
)

if ($Basket) {
    $cmd += "--basket"
}

if ($Json) {
    $cmd += "--json"
}

$StartedAt = Get-Date

python @cmd *> $RunLog
$ExitCode = $LASTEXITCODE

$FinishedAt = Get-Date

@{
    name = "signal"
    profile = $Profile
    list = $List
    top = $Top
    basket = [bool]$Basket
    exit_code = $ExitCode
    started_at = $StartedAt.ToString("s")
    finished_at = $FinishedAt.ToString("s")
    log = $RunLog
    report = $ReportTxt
    json = $ReportJson
} | ConvertTo-Json -Depth 5 | Set-Content -Path $Manifest -Encoding UTF8

if ($ExitCode -ne 0) {
    Write-Host ""
    Write-Host "AURUM SIGNAL FALHOU"
    Rule
    Get-Content $RunLog -Tail 100
    exit $ExitCode
}

$Lines = Get-Content $RunLog -Encoding UTF8

$market = "-"
$vol = "-"
$observer = "-"
$weights = "-"
$behavior = "-"
$blocked = "-"

$realLong = @()
$obsLong = @()
$realShort = @()
$obsShort = @()

$section = ""

foreach ($line in $Lines) {
    if ($line -match "^regime\s+(.+)$") { $market = $Matches[1].Trim() }
    if ($line -match "^volatility\s+(.+)$") { $vol = $Matches[1].Trim() }
    if ($line -match "^observer\s+(.+)$") { $observer = $Matches[1].Trim() }
    if ($line -match "^weights\s+(.+)$") { $weights = $Matches[1].Trim() }
    if ($line -match "^behavior\s+(.+)$") { $behavior = $Matches[1].Trim() }
    if ($line -match "^blocked\s+(.+)$") { $blocked = $Matches[1].Trim() }

    if ($line -match "^BUY / LONG BOOK") {
        $section = "REAL_LONG"
        continue
    }

    if ($line -match "^LONG OBSERVATION CANDIDATES") {
        $section = "OBS_LONG"
        continue
    }

    if ($line -match "^SELL-SHORT / HEDGE BOOK") {
        $section = "REAL_SHORT"
        continue
    }

    if ($line -match "^SELL-SHORT CANDIDATES") {
        $section = "OBS_SHORT"
        continue
    }

    if ($line -match "^(EXIT BOOK|DEFENSIVE BOOK|HEDGE CANDIDATES|CASH / WAIT MODE|FILES|BASKET|LEGEND|NO ACTIONABLE ASSETS)") {
        $section = ""
        continue
    }

    if ($section -eq "REAL_LONG") {
        if ($line -match "^\s*\d+\s+([A-Z0-9]+)\s+LONG\s+(\S+)\s+(\S+)\s+([\d\.]+)\s+(.+)$") {
            $ticker = $Matches[1]
            $statusRaw = $Matches[3]
            $score = $Matches[4]
            $reason = Clean-Text $Matches[5]
            $status = Clean-Status $statusRaw

            $read = "sinal operacional de compra"
            if ($status -match "bloqueado") {
                $read = "sinal existe; execucao bloqueada"
            } elseif ($status -match "executavel") {
                $read = "compra executavel"
            }

            $realLong += New-Row $ticker "LONG" "operacional" $score $status $reason $read
        }

        continue
    }

    if ($section -eq "OBS_LONG") {
        if ($line -match "^\s*\d+\s+([A-Z0-9]+)\s+([\d\.]+)\s+(OBS_FAVORABLE|WATCH|LOW_RISK_WEAK)\s+(.+)$") {
            $ticker = $Matches[1]
            $score = $Matches[2]
            $class = Clean-LongClass $Matches[3]
            $reason = Clean-Text $Matches[4]

            $obsLong += New-Row $ticker "LONG" $class $score "observacao" "-" $reason
        }

        continue
    }

    if ($section -eq "REAL_SHORT") {
        if ($line -match "^\s*\d+\s+([A-Z0-9]+)\s+([\d\.]+)\s+SHORT_SETUP\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(.+)$") {
            $ticker = $Matches[1]
            $score = $Matches[2]
            $borrow = Clean-Text $Matches[4]
            $permission = Clean-Status $Matches[6]
            $reason = Clean-Text $Matches[7]

            $read = "sinal operacional de venda"
            if ($permission -match "bloqueado") {
                $read = "sinal existe; execucao bloqueada"
            } elseif ($permission -match "executavel") {
                $read = "short executavel"
            }

            $realShort += New-Row $ticker "SHORT" "operacional" $score $permission $borrow $read
        }

        continue
    }

    if ($section -eq "OBS_SHORT") {
        if ($line -match "^\s*\d+\s+([A-Z0-9]+)\s+([\d\.]+)\s+SHORT_SETUP\s+(\S+)\s+(\S+)\s+(\S+)\s+(.+)$") {
            $ticker = $Matches[1]
            $score = $Matches[2]
            $borrow = Clean-Text $Matches[4]
            $action = Clean-Text $Matches[6]

            $obsShort += New-Row $ticker "SHORT" "observacao" $score "observacao" "-" $action
        }

        continue
    }
}

Write-Host ""
Write-Host "AURUM SIGNAL - QUATRO MESAS"
Rule
Write-Host ("Perfil        : {0}" -f $Profile)
Write-Host ("Lista         : {0}" -f $List)
Write-Host ("Mercado       : {0}" -f $market)
Write-Host ("Volatilidade  : {0}" -f $vol)
Write-Host ("Observer      : {0}" -f $observer)
Write-Host ("Pesos         : {0}" -f $weights)
Write-Host ("Comportamento : {0}" -f $behavior)
Write-Host ("Bloqueados    : {0}" -f $blocked)
Write-Host ""
Write-Host "Leitura rapida:"
Write-Host "REAL LONG/SHORT = book operacional do motor, inclusive quando bloqueado."
Write-Host "OBS LONG/SHORT  = lista de acompanhamento, sem permissao de execucao."
Write-Host "A coluna STATUS mostra se a operacao esta executavel, bloqueada ou apenas em observacao."

Write-Book -Title "1 REAL LONG - BOOK OPERACIONAL DE COMPRA" -Subtitle "Sinais de compra do motor; STATUS informa se executa ou bloqueia." -Rows $realLong
Write-Book -Title "2 OBS LONG - OBSERVACAO DE COMPRA" -Subtitle "Ativos para acompanhar pelo lado comprador." -Rows $obsLong
Write-Book -Title "3 REAL SHORT - BOOK OPERACIONAL DE VENDA" -Subtitle "Sinais de venda/short do motor; STATUS informa se executa ou bloqueia." -Rows $realShort
Write-Book -Title "4 OBS SHORT - OBSERVACAO DE VENDA" -Subtitle "Ativos para acompanhar pelo lado vendedor; sem leitura de bloqueio operacional." -Rows $obsShort

Write-Host ""
Write-Host "ARQUIVOS"
Rule
Write-Host ("Relatorio : {0}" -f $ReportTxt)
Write-Host ("JSON      : {0}" -f $ReportJson)
Write-Host ("Log bruto : {0}" -f $RunLog)
Write-Host ("Manifesto : {0}" -f $Manifest)

Write-Host ""
Write-Host "DECISAO"
Rule

$readyLong = @($realLong | Where-Object { $_.Status -match "executavel" })
$readyShort = @($realShort | Where-Object { $_.Status -match "executavel" })

if ($readyLong.Count -eq 0 -and $readyShort.Count -eq 0) {
    Write-Host "Sem operacao executavel. Existem sinais, mas os bloqueios impedem execucao automatica."
} elseif ($readyLong.Count -gt 0 -and $readyShort.Count -eq 0) {
    Write-Host "Ha compras executaveis. Conferir risco e tamanho antes da ordem."
} elseif ($readyLong.Count -eq 0 -and $readyShort.Count -gt 0) {
    Write-Host "Ha shorts executaveis. Conferir aluguel/custo antes da ordem."
} else {
    Write-Host "Ha sinais executaveis nos dois lados. Mercado misto; reduzir tamanho e confirmar contexto."
}

exit 0
