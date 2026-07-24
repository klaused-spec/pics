# PICS - Personal Image & Content System

Sistema organizador de fotos e videos pessoais com reconhecimento facial, busca por IA (Azure OpenAI) e app Android.

## Funcionalidades

- Organizacao automatica por ano/mes
- Deduplicacao por SHA-256
- Reconhecimento facial (InsightFace/ONNX)
- Busca semantica via Azure OpenAI
- Streaming HLS de videos no app Android
- Sync com OneDrive via rclone
- App Android (APK) com viewer, zoom, slideshow e compartilhamento

## Estrutura

```
pics/
  backend/        FastAPI + SQLite + workers de IA
  frontend/       React (Vite) â€” interface web
  mobile/         React Native (Expo) â€” app Android
  tools/          Scripts PowerShell (build APK, status, rclone)
  Caddyfile       Reverse proxy HTTPS
  install.ps1     Instalador para novo PC Windows
  start.bat       Sobe backend + Caddy
```

## Instalacao (novo PC Windows)

> **Requer PowerShell 7+.** O PS 5.1 (padrao do Windows) nao e compativel com o instalador.
> Instale antes:
> ```powershell
> winget install --id Microsoft.PowerShell --accept-package-agreements --accept-source-agreements
> ```
> Ou baixe o MSI em: https://github.com/PowerShell/PowerShell/releases/latest

Depois de instalar o PS7, rode:

```powershell
pwsh -ExecutionPolicy Bypass -File install.ps1
```

Requisitos: Python 3.x, Node.js (para build do frontend), acesso a internet.

O instalador faz automaticamente:
- Cria o venv Python e instala `requirements.txt`
- Baixa e instala Caddy em `tools\caddy\`
- Detecta/instala ffmpeg
- Configura o `.env` com os caminhos do novo PC

## Rodar

```
start.bat
```

- HTTP local:  http://localhost:8080
- HTTPS:       https://seu-dominio:8443 (requer cert â€” ver SSL_SETUP.md)

## Backend manual

```powershell
cd backend
venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Variaveis de ambiente principais

Copie `backend\.env.example` para `backend\.env` e ajuste:

| Variavel              | Descricao                                                  |
|-----------------------|------------------------------------------------------------|
| `SOURCE_DIR`          | Pasta onde ficam as fotos originais                        |
| `ORGANIZED_DIR`       | Pasta onde o app organiza as fotos                         |
| `DATABASE_URL`        | Caminho do SQLite (`sqlite:///C:/src/pics/backend/pics.db`)|
| `FFMPEG_PATH`         | Caminho do ffmpeg.exe                                      |
| `FFPROBE_PATH`        | Caminho do ffprobe.exe                                     |
| `AZURE_OPENAI_*`      | Credenciais Azure OpenAI (opcional)                        |
| `RCLONE_ENABLED`      | `true` para sync automatico com OneDrive                   |
| `SECRET_KEY`          | Chave JWT â€” mude em producao                               |

## rclone / OneDrive

Config em `tools\rclone\rclone.conf`. Ver `backend\RCLONE_GUIDE.md`.

## SSL

Ver `SSL_SETUP.md` para emitir certificado via certbot (DNS-01 Hostinger).

## App Android

O APK mais recente fica em `mobile\pics-mobile-debug-apk\app-release.apk`.

Para buildar um novo APK:
```powershell
powershell -ExecutionPolicy Bypass -File tools\dispatch-apk.ps1
# aguarda ~15 min
powershell -ExecutionPolicy Bypass -File tools\dl-apk.ps1
```

## Creditos

Desenvolvido por **klawzedo** (klawzedo@gmail.com).

Construido com o auxilio de [GitHub Copilot](https://github.com/features/copilot) (claude-sonnet-4-6), com aproximadamente 3,5 milhoes de tokens consumidos durante o desenvolvimento.
