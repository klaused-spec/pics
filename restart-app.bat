@echo off
chcp 65001 >nul
:: Mata processos existentes
taskkill /F /IM python.exe /T >nul 2>&1
taskkill /F /IM caddy.exe /T >nul 2>&1
:: Aguarda 2 segundos para portas liberarem
timeout /t 2 /nobreak >nul
:: Sobe tudo novamente (sem janela interativa, sem pause)
set "ROOT=%~dp0"
start "PICS Backend" cmd /k call "%ROOT%start-backend.bat"
:: Aguarda backend ficar pronto (até 60s)
set /A TRIES=0
:wait
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/health' -UseBasicParsing -TimeoutSec 3 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if %ERRORLEVEL% EQU 0 goto caddy_start
if %TRIES% GEQ 30 goto caddy_start
set /A TRIES+=1
timeout /t 2 /nobreak >nul
goto wait
:caddy_start
start "PICS Caddy" "C:\caddy\caddy.exe" run --config "%ROOT%Caddyfile"
