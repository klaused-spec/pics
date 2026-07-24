param(
    [switch]$NoBuild,
    [switch]$RestartBackend
)

$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $Root

Write-Host "=== PICS Update ===" -ForegroundColor Cyan

# 1. Git pull
Write-Host "`n[1/3] Git pull..." -ForegroundColor Yellow
git pull
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: git pull falhou." -ForegroundColor Red
    exit 1
}

# 2. Build frontend
if (-not $NoBuild) {
    Write-Host "`n[2/3] Build do frontend..." -ForegroundColor Yellow
    Set-Location "$Root\frontend"
    npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERRO: build falhou." -ForegroundColor Red
        exit 1
    }
    Set-Location $Root
    Write-Host "Build concluido." -ForegroundColor Green
} else {
    Write-Host "`n[2/3] Build ignorado (-NoBuild)." -ForegroundColor Gray
}

# 3. Reiniciar backend (opcional)
if ($RestartBackend) {
    Write-Host "`n[3/3] Reiniciando backend..." -ForegroundColor Yellow
    cmd /c "$Root\restart-app.bat"
} else {
    Write-Host "`n[3/3] Backend NAO reiniciado (use -RestartBackend para reiniciar)." -ForegroundColor Gray
}

Write-Host "`n=== Concluido ===" -ForegroundColor Cyan
