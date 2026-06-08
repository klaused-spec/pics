#!/bin/bash
# Script de setup completo para WSL / Ubuntu
# Instala todas as dependências de sistema, Python 3.11, Node.js 20, e pacotes do projeto

set -e

echo "=== PICS - Setup Completo ==="
echo ""

# Detectar se é Debian/Ubuntu
if ! command -v apt-get &> /dev/null; then
    echo "ERRO: Este script suporta apenas sistemas baseados em Debian/Ubuntu (apt-get)"
    exit 1
fi

# 1. Dependências de sistema
echo "[1/5] Instalando dependências de sistema..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    software-properties-common \
    curl \
    wget \
    ffmpeg \
    libjpeg-dev \
    libpng-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    build-essential \
    > /dev/null 2>&1
echo "  [OK] Dependências de sistema instaladas"

# 2. Python 3.11
echo "[2/5] Verificando Python 3.11..."
if ! command -v python3.11 &> /dev/null; then
    echo "  >> Instalando Python 3.11..."
    sudo add-apt-repository -y ppa:deadsnakes/ppa > /dev/null 2>&1
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3.11 python3.11-venv python3.11-dev > /dev/null 2>&1
    echo "  [OK] Python 3.11 instalado"
else
    echo "  [OK] Python 3.11 já disponível ($(python3.11 --version))"
fi

# 3. Node.js 20
echo "[3/5] Verificando Node.js..."
NODE_MAJOR=20
if ! command -v node &> /dev/null || [[ $(node --version | cut -d. -f1 | tr -d 'v') -lt $NODE_MAJOR ]]; then
    echo "  >> Instalando Node.js $NODE_MAJOR..."
    curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | sudo -E bash - > /dev/null 2>&1
    sudo apt-get install -y -qq nodejs > /dev/null 2>&1
    echo "  [OK] Node.js $(node --version) instalado"
else
    echo "  [OK] Node.js já disponível ($(node --version))"
fi

# 4. Backend Python
echo "[4/5] Configurando backend..."
cd backend

if [ ! -d "venv" ]; then
    python3.11 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  >> Criado .env a partir do .env.example"
fi
echo "  [OK] Backend configurado"

cd ..

# 5. Frontend
echo "[5/5] Configurando frontend..."
cd frontend
npm install --silent 2>/dev/null
cd ..
echo "  [OK] Frontend configurado"

# Baixar modelos se ainda não existem
if [ ! -f "backend/models/w600k_r50.onnx" ]; then
    echo ""
    echo ">> Modelos ONNX não encontrados. Executando download..."
    chmod +x download-models.sh
    ./download-models.sh
fi

echo ""
echo "========================================="
echo "  Setup completo!"
echo "========================================="
echo ""
echo "  PRÓXIMOS PASSOS:"
echo ""
echo "  1. Configure backend/.env com suas credenciais:"
echo "     nano backend/.env"
echo ""
echo "  2. Inicie o backend (terminal 1):"
echo "     cd backend && source venv/bin/activate"
echo "     uvicorn app.main:app --reload --port 8000"
echo ""
echo "  3. Inicie o frontend (terminal 2):"
echo "     cd frontend && npm run dev"
echo ""
echo "  4. Acesse: http://localhost:5173"
echo ""
echo "  - ORGANIZED_DIR (pasta destino organizada)"
