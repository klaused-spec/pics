@echo off
chcp 65001 >nul
cd /d "%~dp0backend" || (
    echo [ERRO] Nao foi possivel acessar %~dp0backend
    rem pause
    exit /b 1
)

set "PYTHONCMD=python"
where %PYTHONCMD% >nul 2>&1
if errorlevel 1 (
    if exist "%ProgramFiles%\Python312\python.exe" (
        set "PYTHONCMD=%ProgramFiles%\Python312\python.exe"
    ) else if exist "%ProgramFiles(x86)%\Python312\python.exe" (
        set "PYTHONCMD=%ProgramFiles(x86)%\Python312\python.exe"
    ) else (
        echo [ERRO] Python nao encontrado. Instale Python 3.12 e adicione ao PATH.
        rem pause
        exit /b 1
    )
)

if not exist "logs" mkdir logs

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    if errorlevel 1 (
        echo [AVISO] Falha ao ativar o venv. Continuando com Python global.
    ) else (
        set "PYTHONCMD=python"
    )
) else (
    echo [WARN] venv nao encontrado. Usando Python global.
)

echo Iniciando backend em http://0.0.0.0:8000 ...
"%PYTHONCMD%" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
rem pause
exit