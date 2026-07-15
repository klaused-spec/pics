@echo off
REM Script para matar processo na porta 8000 e reiniciar backend

echo [*] Matando processos na porta 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| find ":8000"') do (
    taskkill /PID %%a /F 2>nul
    echo [+] Matou processo %%a
)

echo [*] Aguardando 2 segundos...
timeout /t 2 /nobreak

echo [*] Iniciando backend...
cd /d c:\src\pics\backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
