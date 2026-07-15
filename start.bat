@echo off
chcp 65001 >nul
title PICS - Backend + Caddy HTTPS
color 0A
setlocal

echo.
echo ========================================
echo === PICS - Sistema de Fotos e IA ===
echo ========================================
echo.
echo [INFO] Iniciando backend + Caddy HTTPS nativamente no Windows...

set "ROOT=%~dp0"
set "CADDY_EXE=C:\caddy\caddy.exe"
set "CADDYFILE=%ROOT%Caddyfile"
set "FRONTEND_DIST=%ROOT%frontend\dist"
set "PUBLIC_URL=https://pics.meulavoro.com.br:8443"

if not exist "%ROOT%start-backend.bat" goto err_backend
if not exist "%CADDY_EXE%" goto err_caddy
if not exist "%CADDYFILE%" goto err_caddyfile
if not exist "%FRONTEND_DIST%\index.html" goto build_front
goto run_all

:build_front
echo [AVISO] Build do frontend nao encontrado. Gerando com npm run build...
pushd "%ROOT%frontend"
call npm run build
popd
if not exist "%FRONTEND_DIST%\index.html" goto err_build
goto run_all

:run_all
echo [INFO] Abrindo backend em uma nova janela...
start "PICS Backend" cmd /k call "%ROOT%start-backend.bat"

echo [INFO] Aguardando backend ficar pronto...
set "BACKEND_URL=http://127.0.0.1:8000/api/health"
set /A BACKEND_TRIES=0
set /A BACKEND_MAX_TRIES=30

:wait_backend
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri '%BACKEND_URL%' -UseBasicParsing -TimeoutSec 3 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if %ERRORLEVEL% EQU 0 goto backend_ok
if %BACKEND_TRIES% GEQ %BACKEND_MAX_TRIES% goto err_timeout
set /A BACKEND_TRIES+=1
timeout /t 2 /nobreak >nul
goto wait_backend

:backend_ok
echo [INFO] Backend disponivel.
echo [INFO] Abrindo Caddy em uma nova janela...
start "PICS Caddy" "%CADDY_EXE%" run --config "%CADDYFILE%"

echo.
echo [OK] Backend e Caddy iniciados.
echo      Acesso local:    https://localhost:8443
echo      Acesso externo:  %PUBLIC_URL%
echo.
echo Pressione qualquer tecla para fechar esta janela de controle.
pause >nul
goto :eof

:err_backend
echo [ERRO] start-backend.bat nao encontrado em %ROOT%
pause
goto :eof

:err_caddy
echo [ERRO] Caddy nao encontrado em %CADDY_EXE%
echo        Baixe em https://caddyserver.com/download e salve como %CADDY_EXE%
pause
goto :eof

:err_caddyfile
echo [ERRO] Caddyfile nao encontrado em %CADDYFILE%
pause
goto :eof

:err_build
echo [ERRO] Falha ao gerar o build do frontend.
pause
goto :eof

:err_timeout
echo [ERRO] Timeout aguardando backend em %BACKEND_URL%.
echo        Verifique se o backend iniciou corretamente e tente novamente.
pause
goto :eof
