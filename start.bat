@echo off
chcp 65001 >nul
setlocal
set "ROOT=%~dp0"

echo.
echo ========================================
echo    PICS - Sistema de Fotos e IA
echo ========================================
echo.

:: ── Modo via argumento ou pergunta interativa ──────────────────────────────
set "MODE=%~1"
if /i "%MODE%"=="dev"  goto mode_dev
if /i "%MODE%"=="prod" goto mode_prod

echo  Escolha o modo de inicializacao:
echo    [1] dev  - HTTP puro (backend :8000 + frontend Vite :5173)
echo    [2] prod - HTTPS via Caddy (:8443) com build de producao
echo.
set /p CHOICE= Opcao [1/2]: 
if "%CHOICE%"=="1" goto mode_dev
if "%CHOICE%"=="2" goto mode_prod
echo [ERRO] Opcao invalida.
pause & goto :eof

:: ── MODO DEV ───────────────────────────────────────────────────────────────
:mode_dev
title PICS - Modo DEV (HTTP)
color 0B
echo [DEV] Backend em http://localhost:8000
echo [DEV] Frontend em http://localhost:5173
echo.
start "PICS Backend" cmd /k call "%ROOT%start-backend.bat"
start "PICS Frontend" cmd /k "cd /d %ROOT%frontend && npm run dev"
echo.
echo [OK] Ambos iniciados. Acesse http://localhost:5173
echo Pressione qualquer tecla para fechar esta janela.
pause >nul
goto :eof

:: ── MODO PROD ──────────────────────────────────────────────────────────────
:mode_prod
title PICS - Modo PROD (HTTPS)
color 0A

:: Procura caddy na pasta local primeiro, depois em C:\caddy\
set "CADDY_EXE=%ROOT%tools\caddy\caddy.exe"
if not exist "%CADDY_EXE%" set "CADDY_EXE=C:\caddy\caddy.exe"
set "CADDYFILE=%ROOT%Caddyfile"
set "FRONTEND_DIST=%ROOT%frontend\dist"

if not exist "%CADDY_EXE%"          goto err_caddy
if not exist "%CADDYFILE%"          goto err_caddyfile
if not exist "%FRONTEND_DIST%\index.html" goto build_front
goto run_prod

:build_front
echo [AVISO] Build do frontend nao encontrado. Gerando...
pushd "%ROOT%frontend"
call npm run build
popd
if not exist "%FRONTEND_DIST%\index.html" goto err_build

:run_prod
echo [INFO] Iniciando backend...
start "PICS Backend" cmd /k call "%ROOT%start-backend.bat"

echo [INFO] Aguardando backend...
set /A T=0
:wait_be
powershell -NoProfile -Command "try{Invoke-WebRequest http://127.0.0.1:8000/api/health -UseBasicParsing -TimeoutSec 2|Out-Null;exit 0}catch{exit 1}" >nul 2>&1
if %ERRORLEVEL%==0 goto be_ok
if %T% GEQ 30 goto err_timeout
set /A T+=1
timeout /t 2 /nobreak >nul
goto wait_be

:be_ok
echo [INFO] Backend disponivel. Iniciando Caddy...
start "PICS Caddy" "%CADDY_EXE%" run --config "%CADDYFILE%"
echo.
echo [OK] Pronto.
echo      HTTP local (sem SSL): http://localhost:8080
echo      HTTPS:                https://localhost:8443
echo.
pause >nul
goto :eof

:err_caddy
echo [ERRO] caddy.exe nao encontrado.
echo        Execute install.ps1 ou coloque caddy.exe em tools\caddy\
pause & goto :eof

:err_caddyfile
echo [ERRO] Caddyfile nao encontrado em %ROOT%
pause & goto :eof

:err_build
echo [ERRO] Falha no build do frontend.
pause & goto :eof

:err_timeout
echo [ERRO] Backend nao respondeu em 60s.
pause & goto :eof

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
