@echo off
chcp 65001 >nul
cd /d "%~dp0backend"
if not exist "logs" mkdir logs
call venv\Scripts\activate.bat
echo Iniciando backend em http://localhost:8000 ...
uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
