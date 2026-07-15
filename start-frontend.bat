@echo off
chcp 65001 >nul
cd /d "%~dp0frontend" || (
    echo [ERRO] Nao foi possivel acessar %~dp0frontend
    pause
    exit /b 1
)
if not exist "node_modules" (
    echo [ERRO] Dependencias do frontend nao encontradas.
    echo        Execute setup.bat para instalar node_modules.
    pause
    exit /b 1
)
echo Iniciando frontend em http://localhost:5173 ...
call npm run dev
pause
