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
uvicorn app.main:app --host 0.0.0.0 --port 8000 2>&1 | tee logs/backend.log &
BACKEND_PID=$!

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
