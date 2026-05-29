# PICS - Personal Image & Content System

Sistema organizador de fotos e vídeos pessoais com reconhecimento facial, de locais e busca inteligente via Azure OpenAI.

## Funcionalidades

- **Organização automática**: Importa fotos/vídeos e organiza por ano/mês
- **Padrão de pastas configurável**: Hierárquico (`YYYY/MM/`) ou flat (`YYYY_MM/`)
- **Múltiplas pastas de biblioteca**: Indexa várias pastas de destino simultaneamente
- **Detecção de duplicatas**: SHA256 por conteúdo (não por nome — suporta câmeras diferentes)
- **Reconhecimento facial**: Detecta e agrupa rostos com ArcFace + MediaPipe
- **Descrição de cenas**: Azure OpenAI Vision descreve conteúdo, locais e contexto
- **Busca inteligente**: Busca por texto livre, data, extensão, nome
- **Interface web**: Galeria, player de vídeo, slideshow, drag-select
- **Backup/Restore**: ZIP com banco completo (faces, AI, albums) — portátil entre PCs
- **Configurações via UI**: Paths, padrão de organização e pastas extras configuráveis
- **Nunca deleta**: Arquivos só são movidos (source → organized → trash)

## Setup Rápido (novo PC com WSL)

```bash
# 1. Instalar pré-requisitos (Python 3.12 — NÃO usar 3.13+)
sudo apt update && sudo apt install -y software-properties-common ffmpeg git
sudo add-apt-repository -y ppa:deadsnakes/ppa && sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev

# 2. Instalar Node.js (via nvm)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc
nvm install 20

# 3. Clonar o repositório
git clone https://github.com/klaused-spec/pics.git
cd pics

# 4. Setup backend
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. Setup frontend
cd ../frontend
npm install

# 6. Configurar paths (criar .env no backend)
cat > ../backend/.env << 'EOF'
SOURCE_DIR=/mnt/hd4tb/OneDrive/Pictures/Camera Roll
ORGANIZED_DIR=/mnt/hd4tb/Fotos
TRASH_DIR=/mnt/hd4tb/Fotos/.trash
ORGANIZATION_PATTERN=year_month
LIBRARY_FOLDERS=/mnt/g/fotos/pasta1,/mnt/g/fotos/pasta2
AZURE_OPENAI_ENDPOINT=https://seu-endpoint.openai.azure.com/
AZURE_OPENAI_KEY=sua-chave-aqui
AZURE_OPENAI_DEPLOYMENT=gpt-4o
EOF

# 7. Montar HD 4TB (se externo)
sudo mkdir -p /mnt/hd4tb
sudo mount /dev/sdX1 /mnt/hd4tb  # ajuste o device

# 8. Iniciar (2 terminais ou use start.sh)
# Terminal 1 - Backend:
cd backend && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000
# Terminal 2 - Frontend:
cd frontend && npm run dev
```

Acesse: **http://localhost:5173**

## Após o Clone

1. Abra **Configurações** (ícone ⚙️ na sidebar)
2. Ajuste os paths de **Source**, **Organizadas** e **Trash** para o seu HD
3. Escolha o **Padrão de Organização**:
   - **Hierárquico** (`YYYY/MM/`): ex: `2021/05/foto.jpg`
   - **Flat** (`YYYY_MM/`): ex: `2021_05/foto.jpg` — permite pastas manuais como `2021_05_aniversario_fulano/`
4. Adicione **Pastas de Biblioteca** extras se tiver fotos em vários locais (ex: `/mnt/g/fotos/pasta1`, `/mnt/g/fotos/pasta2`)
5. Clique **Salvar**
6. Vá em **Início** e clique **Escanear** — o sistema organiza tudo automaticamente

### Padrão de Organização Flat

No modo flat, pastas como `2021_05/` e `2021_05_aniversario_fulano/` coexistem **separadas** — o sistema não agrupa nem mescla.
Útil para quem já tem coleções organizadas manualmente com descrição no nome da pasta.

## Migração entre PCs

1. No PC antigo: **Configurações → Backup** (baixa ZIP com banco + configs)
2. No PC novo: clone o repo, rode setup, monte o HD
3. **Configurações → Restaurar** (sobe o ZIP)
4. Ajuste os paths se o ponto de montagem mudou
5. Tudo funciona: faces, descrições IA, albums — tudo linkado por SHA256

## Pré-requisitos

- **WSL2** (Ubuntu 22.04+) ou Linux nativo
- **Python 3.12** (⚠️ Python 3.13+ NÃO funciona — mediapipe/onnxruntime não têm builds)
- **Node.js 18+** (recomendado 20)
- **ffmpeg** (`sudo apt install ffmpeg`)
- Conta **Azure OpenAI** com deployment GPT-4o (opcional, para descrição de cenas)

### Instalar Python 3.12 (Ubuntu/WSL)

```bash
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev
python3.12 --version
```

## Configuração (.env)

| Variável | Descrição |
|----------|-----------|
| `SOURCE_DIR` | Pasta de origem das fotos (ex: `/mnt/hd4tb/OneDrive/Pictures`) |
| `ORGANIZED_DIR` | Pasta destino organizada (ex: `/mnt/hd4tb/Fotos`) |
| `TRASH_DIR` | Lixeira (ex: `/mnt/hd4tb/Fotos/.trash`) |
| `AZURE_OPENAI_ENDPOINT` | Endpoint do Azure OpenAI |
| `AZURE_OPENAI_KEY` | Chave de API |
| `AZURE_OPENAI_DEPLOYMENT` | Nome do deployment (ex: `gpt-4o`) |

Também configurável via UI em **Configurações**.

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

## Setup Real — Troubleshooting & Soluções (Ubuntu 26.04)

Documentação dos problemas encontrados e soluções ao fazer setup em ambiente real:

### Problema 1: Pacote `libgl1-mesa-glx` não disponível
**Erro**: `E: Package 'libgl1-mesa-glx' has no installation candidate`

**Solução**: 
```bash
# Instale as demais dependências sem libgl1-mesa-glx
sudo apt install -y curl wget ffmpeg libjpeg-dev libpng-dev libglib2.0-0 build-essential software-properties-common

# Para sistemas que precisam de OpenGL, instale alternativas:
sudo apt install -y libgl1 libgl1-mesa-dri
```

### Problema 2: Python 3.12 não disponível (ou mediapipe/onnxruntime falham com 3.13+)
**Erro**: Python 3.13+ trava mediapipe/onnxruntime na compilação

**Solução**: Use **Python 3.11** (via deadsnakes) se 3.12 não estiver disponível:
```bash
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev

# Depois crie o venv com 3.11
cd backend
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Setup Automático Completo (sem nvm)
Se `setup.sh` travar ou você preferir fazer manualmente:

```bash
# 1. Sistema & dependências
sudo apt update && sudo apt install -y curl wget ffmpeg build-essential libpng-dev libjpeg-dev

# 2. Python 3.11/3.12 (dependendo do que estiver disponível)
sudo add-apt-repository -y ppa:deadsnakes/ppa && sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev  # ou python3.12

# 3. Node.js 20 (via NodeSource, sem nvm)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash -
sudo apt install -y nodejs

# 4. Backend
cd backend
python3.11 -m venv venv  # ou python3.12
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 5. Frontend
cd ../frontend
npm install

# 6. Modelos ONNX
cd ..
chmod +x download-models.sh
./download-models.sh

# 7. Configuração .env
cp backend/.env.example backend/.env
# Edite backend/.env com seus paths e chaves Azure
nano backend/.env

# 8. Iniciar (2 terminais)
# Terminal 1:
cd backend && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000

# Terminal 2:
cd frontend && npm run dev
```

### Verificação Pós-Setup
```bash
# Backend venv criado?
ls -la backend/venv/bin/python

# Node modules instalados?
ls -la frontend/node_modules | wc -l

# Modelos baixados?
ls -la backend/models/*.onnx

# .env criado?
cat backend/.env | grep SOURCE_DIR
```

## Notas para WSL

- Para acessar fotos do Windows: monte via `/mnt/c/Users/SeuUsuario/...`
- Para HDs externos/internos no WSL2: `sudo mount /dev/sdX1 /mnt/hd4tb`
- Para montar automaticamente no boot, adicione ao `/etc/fstab`:
  ```
  /dev/sdb1 /mnt/hd4tb ext4 defaults 0 2
  ```
- O SQLite funciona bem para uso pessoal; o banco fica em `backend/pics.db`
- Modelos ONNX (~330MB) ficam em `backend/models/` e NÃO são versionados no git

## Contribuir & Deploy

### Clonar & Fazer Setup
```bash
git clone https://github.com/klaused-spec/pics.git
cd pics
./setup.sh  # ou use os passos manuais acima se tiver problemas
```

### Fazer Commit
```bash
git add .
git commit -m "docs: adiciona troubleshooting setup real (Python 3.11, libgl1-mesa-glx)"
git push origin main
```

### Variáveis de Ambiente Obrigatórias
Antes de rodar, crie `backend/.env`:
```env
SOURCE_DIR=/caminho/para/fotos/origem
ORGANIZED_DIR=/caminho/para/fotos/organizadas
TRASH_DIR=/caminho/para/fotos/.trash
DATABASE_URL=sqlite:///./pics.db
HOST=0.0.0.0
PORT=8000
```

Opcionais (para IA):
```env
AZURE_OPENAI_ENDPOINT=https://seu-recurso.openai.azure.com/
AZURE_OPENAI_KEY=sua-chave-aqui
AZURE_OPENAI_DEPLOYMENT=gpt-4o
```
