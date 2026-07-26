@echo off
chcp 65001 >nul
setlocal
set "ROOT=%~dp0"

echo.
echo ========================================
echo    PICS - Sistema de Fotos e IA
echo ========================================
echo.

set "MODE=%~1"
if /i "%MODE%"=="dev"        goto mode_dev
if /i "%MODE%"=="prod"       goto mode_prod
if /i "%MODE%"=="update"     goto mode_update
if /i "%MODE%"=="updateprod" goto mode_updateprod

echo  Escolha o modo:
echo    [1] dev        - HTTP puro (backend :8000 + frontend Vite :5173)
echo    [2] prod       - HTTPS via Caddy (:8443) com build de producao
echo    [3] update     - git pull + download APK + restart app
echo    [4] updateprod - git pull + build frontend + download APK + restart app
echo.
set /p CHOICE= Opcao [1/2/3/4]: 
if "%CHOICE%"=="1" goto mode_dev
if "%CHOICE%"=="2" goto mode_prod
if "%CHOICE%"=="3" goto mode_update
if "%CHOICE%"=="4" goto mode_updateprod
echo [ERRO] Opcao invalida.
pause & goto :eof

:mode_dev
title PICS - Modo DEV
echo [DEV] Backend em http://localhost:8000
echo [DEV] Frontend em http://localhost:5173
echo.
start "PICS Backend" cmd /k call "%ROOT%start-backend.bat"
start "PICS Frontend" cmd /k "cd /d %ROOT%frontend && npm run dev"
echo [OK] Acesse http://localhost:5173
pause >nul
goto :eof

:mode_prod
title PICS - Modo PROD
set "CADDY_EXE=%ROOT%tools\caddy\caddy.exe"
if not exist "%CADDY_EXE%" set "CADDY_EXE=C:\caddy\caddy.exe"
set "CADDYFILE=%ROOT%Caddyfile"
set "FRONTEND_DIST=%ROOT%frontend\dist"

if not exist "%CADDY_EXE%" goto err_caddy
if not exist "%CADDYFILE%" goto err_caddyfile
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
echo [INFO] Iniciando Caddy...
start "PICS Caddy" "%CADDY_EXE%" run --config "%CADDYFILE%"
echo.
echo [OK] Pronto.
echo      HTTP local : http://localhost:8080
echo      HTTPS      : https://localhost:8443
echo.
pause >nul
goto :eof

:mode_update
title PICS - Update
echo [UPDATE] Atualizando codigo...
git -C "%ROOT:~0,-1%" pull
echo [UPDATE] Baixando APK mais recente...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%tools\dl-apk.ps1"
echo [UPDATE] Reiniciando app...
wscript.exe "%ROOT%restart-app.vbs"
echo [OK] Update concluido.
pause
goto :eof

:mode_updateprod
title PICS - Update + Prod
echo [UPDATEPROD] Atualizando codigo...
git -C "%ROOT:~0,-1%" pull
echo [UPDATEPROD] Build do frontend...
pushd "%ROOT%frontend"
call npm run build
popd
echo [UPDATEPROD] Baixando APK mais recente...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%tools\dl-apk.ps1"
echo [UPDATEPROD] Reiniciando app...
wscript.exe "%ROOT%restart-app.vbs"
echo [OK] Update + prod concluido.
pause
goto :eof

:err_caddy
echo [ERRO] caddy.exe nao encontrado. Execute install.ps1 primeiro.
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