@echo off
chcp 65001 >nul
set "ROOT=%~dp0"

:: Sobe backend Python (sem matar nada, sem checar servicos)
start "PICS Backend" cmd /k call "%ROOT%start-backend.bat"

:: Aguarda backend ficar pronto (ate 30s)
set /A TRIES=0
:wait
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/health' -UseBasicParsing -TimeoutSec 3 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if %ERRORLEVEL% EQU 0 goto caddy_start
if %TRIES% GEQ 15 goto caddy_start
set /A TRIES+=1
timeout /t 2 /nobreak >nul
goto wait

:caddy_start
start "PICS Caddy" "%ROOT%tools\caddy\caddy.exe" run --config "%ROOT%Caddyfile"
