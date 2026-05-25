#!/bin/bash
# Inicia backend e frontend em paralelo
# Ctrl+C encerra ambos

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cleanup() {
    echo ""
    echo "Encerrando..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM

# Backend
echo "[PICS] Iniciando backend na porta 8000..."
cd "$SCRIPT_DIR/backend"
source venv/bin/activate
mkdir -p logs
uvicorn app.main:app --host 0.0.0.0 --port 8000 > logs/backend.log 2>&1 &
BACKEND_PID=$!

# Aguardar backend ficar pronto
echo "[PICS] Aguardando backend ficar pronto..."
for i in $(seq 1 60); do
    if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
        echo "[PICS] Backend pronto! (${i}s)"
        break
    fi
    if [ $i -eq 60 ]; then
        echo "[PICS] ERRO: Backend não respondeu após 60s"
        echo "[PICS] Verifique logs em backend/logs/backend.log"
        kill $BACKEND_PID 2>/dev/null
        exit 1
    fi
    sleep 1
done

# Frontend
echo "[PICS] Iniciando frontend na porta 5173..."
cd "$SCRIPT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "[PICS] Backend:  http://localhost:8000"
echo "[PICS] Frontend: http://localhost:5173"
echo "[PICS] Ctrl+C para encerrar ambos"
echo ""

wait
