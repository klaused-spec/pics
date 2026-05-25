@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ╔══════════════════════════════════════════════════════╗
echo ║     PICS - Setup Inteligente (Windows)              ║
echo ╚══════════════════════════════════════════════════════╝
echo.

set "MISSING=0"
set "INSTALLED=0"

:: ============================================================
:: VERIFICAÇÃO DE PRÉ-REQUISITOS
:: ============================================================

echo [1/6] Verificando pre-requisitos...
echo.

:: --- winget ---
where winget >nul 2>&1
if errorlevel 1 (
    echo [ERRO] winget nao encontrado. Instale o App Installer pela Microsoft Store.
    echo        https://aka.ms/getwinget
    echo.
    pause
    exit /b 1
)

:: --- Python ---
set "HAS_PYTHON=0"
where python >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
    echo [OK] Python !PYVER! encontrado
    set "HAS_PYTHON=1"
)
if "!HAS_PYTHON!"=="0" (
    echo [!!] Python nao encontrado - instalando...
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo [ERRO] Falha ao instalar Python. Instale manualmente: https://python.org/downloads
        set "MISSING=1"
    ) else (
        echo [OK] Python instalado com sucesso
        set "INSTALLED=1"
    )
)
echo.

:: --- Node.js ---
set "HAS_NODE=0"
where node >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=1 delims= " %%v in ('node --version 2^>^&1') do set "NODEVER=%%v"
    echo [OK] Node.js !NODEVER! encontrado
    set "HAS_NODE=1"
)
if "!HAS_NODE!"=="0" (
    echo [!!] Node.js nao encontrado - instalando...
    winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo [ERRO] Falha ao instalar Node.js. Instale manualmente: https://nodejs.org
        set "MISSING=1"
    ) else (
        echo [OK] Node.js instalado com sucesso
        set "INSTALLED=1"
    )
)
echo.

:: --- ffmpeg ---
set "HAS_FFMPEG=0"
where ffmpeg >nul 2>&1
if not errorlevel 1 (
    echo [OK] ffmpeg encontrado
    set "HAS_FFMPEG=1"
)
if "!HAS_FFMPEG!"=="0" (
    echo [!!] ffmpeg nao encontrado - instalando...
    winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo [ERRO] Falha ao instalar ffmpeg. Instale manualmente: https://ffmpeg.org/download.html
        set "MISSING=1"
    ) else (
        echo [OK] ffmpeg instalado com sucesso
        set "INSTALLED=1"
    )
)
echo.

:: --- Visual C++ Build Tools (verifica cl.exe) ---
set "HAS_VCTOOLS=0"
where cl >nul 2>&1
if not errorlevel 1 (
    set "HAS_VCTOOLS=1"
)
if "!HAS_VCTOOLS!"=="0" (
    :: Verifica se VS Build Tools esta instalado mesmo sem cl no PATH
    if exist "%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools" (
        set "HAS_VCTOOLS=1"
    )
    if exist "%ProgramFiles%\Microsoft Visual Studio\2022\BuildTools" (
        set "HAS_VCTOOLS=1"
    )
)
if "!HAS_VCTOOLS!"=="1" (
    echo [OK] Visual C++ Build Tools encontrado
) else (
    echo [!!] Visual C++ Build Tools nao encontrado - instalando...
    echo     (Isso pode demorar alguns minutos)
    winget install Microsoft.VisualStudio.2022.BuildTools --override "--quiet --add Microsoft.VisualStudio.Workload.VCTools" --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo [AVISO] Pode ser necessario instalar manualmente:
        echo         winget install Microsoft.VisualStudio.2022.BuildTools
        set "MISSING=1"
    ) else (
        echo [OK] Visual C++ Build Tools instalado com sucesso
        set "INSTALLED=1"
    )
)
echo.

:: --- Verificar se precisa reiniciar terminal ---
if "!INSTALLED!"=="1" (
    echo ══════════════════════════════════════════════════════
    echo  ATENCAO: Novos programas foram instalados.
    echo  FECHE este terminal e abra um NOVO para que o PATH
    echo  seja atualizado, depois execute setup.bat novamente.
    echo ══════════════════════════════════════════════════════
    echo.
    pause
    exit /b 0
)

if "!MISSING!"=="1" (
    echo [ERRO] Alguns pre-requisitos nao puderam ser instalados.
    echo        Corrija os erros acima e execute setup.bat novamente.
    pause
    exit /b 1
)

echo Todos os pre-requisitos OK!
echo.

:: ============================================================
:: SETUP DO PROJETO
:: ============================================================

:: --- Backend ---
echo [2/6] Criando ambiente virtual Python...
cd /d "%~dp0backend"

if not exist "venv" (
    python -m venv venv
)
call venv\Scripts\activate.bat

echo [3/6] Instalando dependencias Python (pode demorar na primeira vez)...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias Python.
    echo        Verifique se o Visual C++ Build Tools esta funcionando.
    pause
    exit /b 1
)

echo [4/6] Configurando .env...
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
        echo   ^>^> Criado .env a partir do .env.example
    ) else (
        (
            echo SOURCE_DIR=C:\Users\%USERNAME%\OneDrive\Pictures\Camera Roll
            echo ORGANIZED_DIR=%~dp0FOTOS\organized
            echo AZURE_OPENAI_ENDPOINT=
            echo AZURE_OPENAI_KEY=
            echo AZURE_OPENAI_DEPLOYMENT=gpt-4o
        ) > .env
        echo   ^>^> Criado .env com valores padrao
    )
    echo   ^>^> EDITE backend\.env com suas credenciais e paths!
) else (
    echo   ^>^> .env ja existe, mantendo configuracao atual
)

cd /d "%~dp0"

:: --- Frontend ---
echo [5/6] Instalando dependencias do frontend...
cd /d "%~dp0frontend"
call npm install --silent
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias do frontend.
    pause
    exit /b 1
)

cd /d "%~dp0"

:: ============================================================
:: CONCLUÍDO
:: ============================================================

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║  [6/6] Setup completo!                             ║
echo ╠══════════════════════════════════════════════════════╣
echo ║                                                      ║
echo ║  Para executar:                                      ║
echo ║    Terminal 1: start-backend.bat                     ║
echo ║    Terminal 2: start-frontend.bat                    ║
echo ║                                                      ║
echo ║  Acesse: http://localhost:5173                       ║
echo ║                                                      ║
echo ╠══════════════════════════════════════════════════════╣
echo ║  LEMBRETE: Edite backend\.env com:                  ║
echo ║    - AZURE_OPENAI_ENDPOINT                           ║
echo ║    - AZURE_OPENAI_KEY                                ║
echo ║    - SOURCE_DIR (pasta com suas fotos)               ║
echo ║    - ORGANIZED_DIR (pasta destino)                   ║
echo ╚══════════════════════════════════════════════════════╝
echo.
pause
