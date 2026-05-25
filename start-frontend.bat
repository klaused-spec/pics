@echo off
chcp 65001 >nul
cd /d "%~dp0frontend"
echo Iniciando frontend em http://localhost:5173 ...
call npm run dev
pause
