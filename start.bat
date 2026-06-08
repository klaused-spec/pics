@echo off
setlocal enabledelayedexpansion
title PICS - Backend + Frontend
color 0A

echo.
echo ========================================
echo === PICS - Sistema de Fotos e IA ===
echo ========================================
echo.

REM Verificar se WSL está instalado
wsl --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] WSL nao esta instalado ou nao esta no PATH
    echo.
    echo Para usar este script no Windows, instale WSL2:
    echo   https://learn.microsoft.com/pt-br/windows/wsl/install
    echo.
    pause
    exit /b 1
)

REM Usar caminho padrão em home do Linux (WSL)
set "WSLPATH=~/src/pics"

echo [INFO] Usando caminho: %WSLPATH%
echo.

REM Verificar se o diretorio existe no WSL
wsl test -d "!WSLPATH!" 2>nul
if errorlevel 1 (
    echo [AVISO] Diretorio nao encontrado em !WSLPATH!
    echo.
    echo Digite o caminho completo no WSL (ex: ~/Documents/pics ou /home/usuario/pics):
    set /p WSLPATH="Caminho: "
)

REM Verificar se start.sh existe
wsl test -f "!WSLPATH!/start.sh" 2>nul
if errorlevel 1 (
    echo [ERRO] start.sh nao encontrado em !WSLPATH!
    echo.
    echo Verifique:
    echo   - O diretorio PICS existe no WSL
    echo   - O arquivo start.sh existe
    echo   - O caminho esta correto
    echo.
    pause
    exit /b 1
)

echo [OK] Arquivos encontrados
echo.
echo [INFO] Iniciando backend em localhost:8000
echo [INFO] Iniciando frontend em localhost:5173
echo.
echo Pressione Ctrl+C para encerrar ambos os servicos
echo.

REM Executar start.sh no WSL
wsl bash -c "cd '!WSLPATH!' && chmod +x start.sh && sed -i 's/\r$//' start.sh && exec ./start.sh"

if errorlevel 1 (
    if errorlevel 130 (
        echo.
        echo [OK] Servicos interrompidos pelo usuario ^(Ctrl+C^)
    ) else (
        echo.
        echo [ERRO] Falha ao iniciar os servicos
        echo.
        echo Verifique:
        echo   - WSL2 rodando corretamente
        echo   - conda ativado no WSL
        echo   - Node.js instalado no WSL
        echo   - Nenhuma outra instancia de PICS rodando ^(porta 8000 e 5173 livres^)
        echo.
    )
) else (
    echo.
    echo [OK] Servicos encerrados normalmente
)

echo.
pause
