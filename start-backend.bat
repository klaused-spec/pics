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

if exist "venv\Scripts\python.exe" (
    set "PYTHONCMD=venv\Scripts\python.exe"
    if exist "venv\Scripts\activate.bat" call venv\Scripts\activate.bat
) else (
    echo [WARN] venv nao encontrado. Usando Python global.
)

echo Iniciando backend em http://0.0.0.0:8000 ...

:: Verifica se ja existe outro processo escutando na porta 8000
netstat -ano | findstr /R "\<8000\>" | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL%==0 (
    echo [AVISO] Porta 8000 ja esta em uso. Outra instancia do backend ja esta rodando.
    echo [AVISO] Fechando esta janela duplicada...
    timeout /t 3 /nobreak >nul
    exit /b 0
)

:loop
echo [%date% %time%] Iniciando uvicorn...
"%PYTHONCMD%" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > logs\backend.log 2>&1
echo [%date% %time%] uvicorn encerrou com codigo %ERRORLEVEL%. Reiniciando em 5s...
timeout /t 5 /nobreak >nul
goto loop