@echo off
chcp 65001 >nul
title PICS - Run Windows Backend + Frontend

echo Iniciando PICS no Windows...

start "PICS Backend" cmd /k "cd /d "%~dp0backend" && call start-backend.bat"
start "PICS Frontend" cmd /k "cd /d "%~dp0frontend" && call start-frontend.bat"

exit /b 0
