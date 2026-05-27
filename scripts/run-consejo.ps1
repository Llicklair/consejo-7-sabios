<#
.SYNOPSIS
    Lanza el Consejo de los 7 Sabios con animación TUI.

.PARAMETER Atasco
    El problema/atasco a debatir. Si no se pasa, prompt interactivo.

.PARAMETER Mode
    mock | real | claude-code  (default: mock)

.PARAMETER Rounds
    Rondas objetivo en modo clásico (default: 3 para mock, 2 para claude-code).
    Ignorado si -Consensus está activo.

.PARAMETER Speed
    Velocidad de animación (default: 0.3 = pausada y contemplativa)

.PARAMETER Consensus
    Activa el modo conversacional turn-by-turn (solo --mode claude-code).
    Los 9 sabios debaten round-robin hasta unanimidad o cap.

.PARAMETER ConsensusRounds
    Cap de rondas en modo consensus (default: 20).

.EXAMPLE
    .\scripts\run-consejo.ps1 -Atasco "Mejora general"
    .\scripts\run-consejo.ps1 -Atasco "Fix auth" -Mode claude-code -Rounds 2
    .\scripts\run-consejo.ps1 -Atasco "Visión 2026" -Mode claude-code -Consensus
#>

param(
    [string]$Atasco = "",
    [ValidateSet("mock", "real", "claude-code")]
    [string]$Mode = "mock",
    [int]$Rounds = 0,
    [double]$Speed = 0.3,
    [string]$CcModel = "opus",
    [switch]$Consensus,
    [int]$ConsensusRounds = 20
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot  = Split-Path -Parent $scriptDir
Set-Location $repoRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "❌ No encuentro .venv\Scripts\python.exe" -ForegroundColor Red
    Write-Host "   Crea el venv primero:  python -m venv .venv ; .venv\Scripts\pip install -e ." -ForegroundColor Yellow
    exit 1
}

if (-not $Atasco) {
    $Atasco = Read-Host "¿Qué quieres debatir? (Enter para 'Mejora general del proyecto')"
    if (-not $Atasco) { $Atasco = "Mejora general del proyecto" }
}

if ($Rounds -eq 0) {
    $Rounds = if ($Mode -eq "claude-code") { 2 } else { 3 }
}

$env:PYTHONPATH = "src"

if ($Consensus -and $Mode -ne "claude-code") {
    Write-Host "❌ -Consensus solo funciona con -Mode claude-code" -ForegroundColor Red
    exit 1
}

$args = @(
    "-m", "consejo.cli",
    $Atasco,
    "--mode", $Mode,
    "--rounds", $Rounds,
    "--speed", $Speed
)

if ($Mode -eq "claude-code") {
    $args += @("--cc-model", $CcModel)
}

if ($Consensus) {
    $args += @("--consensus", "--consensus-rounds", $ConsensusRounds)
}

Write-Host "🔮 Convocando al Consejo..." -ForegroundColor Cyan
Write-Host "   Tema:   $Atasco" -ForegroundColor Gray
if ($Consensus) {
    Write-Host "   Modo:   $Mode (CONSENSUS, hasta $ConsensusRounds rondas)  ·  Velocidad: $Speed" -ForegroundColor Gray
} else {
    Write-Host "   Modo:   $Mode  ·  Rondas: $Rounds  ·  Velocidad: $Speed" -ForegroundColor Gray
}
Write-Host ""

& .venv\Scripts\python.exe @args
