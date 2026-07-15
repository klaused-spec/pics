@echo off
REM Script agressivo para limpar e reiniciar

echo [*] Matando TODOS os python.exe...
taskkill /F /IM python.exe 2>nul

echo [*] Matando por porta 8000...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8000"') do taskkill /PID %%a /F 2>nul

echo [*] Aguardando 3 segundos...
timeout /t 3 /nobreak

echo [*] Iniciando backend novo...
cd /d c:\src\pics\backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
