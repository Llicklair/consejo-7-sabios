# Sigue en vivo el debate del Consejo más reciente, formateado y legible.
# Uso:  .\watch-debate.ps1
# Se queda escuchando: cada turno aparece en cuanto el sabio lo termina.
# Corta con Ctrl+C. No hay que relanzarlo ni pegar nada más.

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8

$file = Get-ChildItem -Path (Join-Path $PSScriptRoot "consejo-debate-*.jsonl") |
    Sort-Object LastWriteTime | Select-Object -Last 1

if (-not $file) {
    Write-Host "No hay ningún consejo-debate-*.jsonl todavía. Lanza el Consejo primero." -ForegroundColor Yellow
    exit 1
}

Write-Host "Siguiendo: $($file.Name)  (Ctrl+C para salir)`n" -ForegroundColor Cyan

Get-Content -LiteralPath $file.FullName -Wait -Encoding UTF8 | ForEach-Object {
    if (-not $_.Trim()) { return }
    try { $o = $_ | ConvertFrom-Json } catch { Write-Host $_; return }

    if ($o.kind -eq "header") {
        Write-Host ("=" * 70) -ForegroundColor DarkGray
        Write-Host "TEMA: $($o.atasco)" -ForegroundColor White
        Write-Host "Sabios: $($o.sages -join ', ')" -ForegroundColor DarkGray
        Write-Host "Rondas: min $($o.min_rounds) / max $($o.max_rounds)" -ForegroundColor DarkGray
        Write-Host ("=" * 70) -ForegroundColor DarkGray
        return
    }

    $signed = $o.vote.signed
    $tag = if ($signed) { "FIRMA" } else { "BLOQUEA" }
    $color = if ($signed) { "Green" } else { "Yellow" }
    $objs = @($o.vote.objections)

    Write-Host ""
    Write-Host ("[turno {0} - ronda {1}] {2}  -> {3}" -f $o.turn, $o.round, $o.sage_id, $tag) -ForegroundColor $color
    if ($o.message) { Write-Host $o.message -ForegroundColor Gray }
    if ($objs.Count -gt 0) {
        Write-Host "  Objeciones:" -ForegroundColor DarkYellow
        foreach ($ob in $objs) { Write-Host "   - $ob" -ForegroundColor DarkYellow }
    }
}
