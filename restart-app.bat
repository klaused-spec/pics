@echo off
chcp 65001 >nul
set "ROOT=%~dp0"

:: ── 1. Para apenas os processos do PICS (nao toca IIS/Myrtille) ──────────────
:: Mata somente o python do backend (filtra pelo caminho do venv do pics)
powershell -NoProfile -Command ^
  "Get-WmiObject Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*pics*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

:: Mata somente o caddy do pics (pelo caminho do executavel)
powershell -NoProfile -Command ^
  "Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like '*tools\caddy*' -or $_.CommandLine -like '*Caddyfile*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

timeout /t 2 /nobreak >nul

:: ── 2. Garante que IIS e Myrtille estao rodando (sobe se caiu) ───────────────
sc query W3SVC | find "RUNNING" >nul 2>&1
if not %ERRORLEVEL%==0 (
    net start W3SVC >nul 2>&1
    timeout /t 3 /nobreak >nul
)
sc query Myrtille.Services | find "RUNNING" >nul 2>&1
if not %ERRORLEVEL%==0 net start Myrtille.Services >nul 2>&1
sc query Myrtille.Admin.Services | find "RUNNING" >nul 2>&1
if not %ERRORLEVEL%==0 net start Myrtille.Admin.Services >nul 2>&1

:: ── 3. Sobe backend Python ────────────────────────────────────────────────────
start "PICS Backend" cmd /k call "%ROOT%start-backend.bat"

:: Aguarda backend ficar pronto (ate 60s)
set /A TRIES=0
:wait
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/health' -UseBasicParsing -TimeoutSec 3 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if %ERRORLEVEL% EQU 0 goto caddy_start
if %TRIES% GEQ 30 goto caddy_start
set /A TRIES+=1
timeout /t 2 /nobreak >nul
goto wait

:: ── 4. Sobe Caddy ─────────────────────────────────────────────────────────────
:caddy_start
start "PICS Caddy" "%ROOT%tools\caddy\caddy.exe" run --config "%ROOT%Caddyfile"
