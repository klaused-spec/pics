#!/bin/bash
# Script de setup rápido para desenvolvimento local

set -e

echo "=== PICS - Setup de Desenvolvimento ==="
echo ""

# Backend
echo "[1/4] Configurando backend..."
cd backend

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt --quiet

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  >> Criado .env a partir do .env.example"
    echo "  >> EDITE backend/.env com suas credenciais Azure OpenAI!"
fi

cd ..

# Frontend
echo "[2/4] Configurando frontend..."
cd frontend
npm install --silent
cd ..

echo ""
echo "[3/4] Setup completo!"
echo ""
echo "=== Como executar ==="
echo ""
echo "Terminal 1 (Backend):"
echo "  cd backend && source venv/bin/activate"
echo "  uvicorn app.main:app --reload --port 8000"
echo ""
echo "Terminal 2 (Frontend):"
echo "  cd frontend && npm run dev"
echo ""
echo "Acesse: http://localhost:5173"
echo ""
echo "[4/4] Lembrete: Configure backend/.env com:"
echo "  - AZURE_OPENAI_ENDPOINT"
echo "  - AZURE_OPENAI_KEY"
echo "  - SOURCE_DIR (pasta do OneDrive Camera Roll)"
echo "  - ORGANIZED_DIR (pasta destino organizada)"
