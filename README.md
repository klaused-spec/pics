# PICS - Personal Image & Content System

Sistema organizador de fotos e vídeos pessoais com reconhecimento facial, de locais e busca inteligente via Azure OpenAI.

## Funcionalidades

- **Organização automática**: Importa fotos/vídeos e organiza por ano/mês
- **Detecção de duplicatas**: SHA256 + perceptual hash (pHash)
- **Reconhecimento facial**: Detecta e agrupa rostos com ArcFace + MediaPipe
- **Descrição de cenas**: Azure OpenAI Vision descreve conteúdo, locais e contexto
- **Busca inteligente**: Busca por texto livre (ex: "praia dezembro 2025")
- **Interface web**: Galeria, player de vídeo, slideshow, busca

## Pré-requisitos

- **WSL2** (Ubuntu 22.04+ recomendado) ou Linux nativo
- **Python 3.11+**
- **Node.js 18+** (recomendado 20)
- **ffmpeg** (`sudo apt install ffmpeg`)
- Conta **Azure OpenAI** com deployment GPT-4o (para descrição de cenas)

## Quick Start (WSL / Linux)

```bash
# 1. Clone o repositório
git clone https://github.com/klaused-spec/pics.git
cd pics

# 2. Baixe os modelos de reconhecimento facial (~330MB)
chmod +x download-models.sh
./download-models.sh

# 3. Rode o setup (cria venv, instala dependências)
chmod +x setup.sh
./setup.sh

# 4. Configure o backend
cp backend/.env.example backend/.env
nano backend/.env  # preencha suas credenciais

# 5. Inicie o backend (terminal 1)
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# 6. Inicie o frontend (terminal 2)
cd frontend && npm run dev
```

Acesse: **http://localhost:5173**

## Via Docker Compose

```bash
# 1. Clone e configure
git clone https://github.com/klaused-spec/pics.git
cd pics
cp backend/.env.example backend/.env
nano backend/.env

# 2. Baixe os modelos
chmod +x download-models.sh
./download-models.sh

# 3. Suba os containers
docker compose up --build
```

Acesse: **http://localhost:5173**

## Configuração (.env)

Copie `backend/.env.example` para `backend/.env` e preencha:

| Variável | Descrição |
|----------|-----------|
| `AZURE_OPENAI_ENDPOINT` | Endpoint do Azure OpenAI |
| `AZURE_OPENAI_KEY` | Chave de API |
| `AZURE_OPENAI_DEPLOYMENT` | Nome do deployment (ex: `gpt-4o`) |
| `SOURCE_DIR` | Pasta de origem das fotos (ex: `/mnt/c/Users/you/OneDrive/Pictures`) |
| `ORGANIZED_DIR` | Pasta destino organizada |

## Arquitetura

```
pics/
├── backend/          # FastAPI + Python
│   ├── app/
│   │   ├── api/      # Endpoints REST
│   │   ├── core/     # Config, database
│   │   ├── models/   # SQLAlchemy models
│   │   ├── services/ # Lógica de negócio (AI, faces, organizer)
│   │   └── workers/  # Tarefas assíncronas
│   ├── libs/         # InsightFace customizado
│   ├── models/       # Modelos ONNX (não versionados)
│   └── requirements.txt
├── frontend/         # React + Vite + Tailwind
│   ├── src/
│   └── package.json
├── docker-compose.yml
├── download-models.sh  # Script para baixar modelos ONNX
└── setup.sh            # Setup de desenvolvimento
```

## Notas para WSL

- Para acessar fotos do Windows: monte via `/mnt/c/Users/SeuUsuario/...`
- Para HDs externos no WSL: monte com `sudo mount /dev/sdX1 /mnt/meuHD`
- O SQLite funciona bem para uso pessoal; o banco fica em `backend/pics.db`
