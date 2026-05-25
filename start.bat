@echo off
title PICS - Backend + Frontend
echo === PICS - Iniciando via WSL ===
echo.
echo Mantendo janela aberta... Feche com Ctrl+C ou feche a janela.
echo.
wsl bash -c "cd ~/src/pics && chmod +x start.sh && ./start.sh"
echo.
echo [PICS] Encerrado.
pause
