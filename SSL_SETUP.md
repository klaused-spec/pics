# HTTPS com Caddy + Let's Encrypt (DNS-01 Hostinger)

Guia para servir o Pics em `https://pics.meulavoro.com.br` usando **Caddy** como
reverse proxy no Windows, com certificado Let's Encrypt renovado automaticamente
via **DNS-01** (não precisa abrir a porta 80).

## Arquitetura

```
Internet
   │  HTTPS (443)
   ▼
Caddy (Windows)  ──/api/*──►  uvicorn  (127.0.0.1:8000)
                 ──restante─►  frontend build (C:\src\pics\frontend\dist)
```

- O navegador e o app mobile falam **só HTTPS na 443**.
- As portas **8000** (backend) e **5173** (Vite dev) **não precisam ficar expostas** à internet.

---

## 1. DNS na Hostinger

Crie um registro **A** apontando o subdomínio para o IP público da sua máquina:

| Tipo | Nome   | Valor            | TTL  |
|------|--------|------------------|------|
| A    | `pics` | `SEU_IP_PUBLICO` | auto |

> Se o IP público for dinâmico, mantenha um DDNS atualizando esse registro A.

## 2. Token da API da Hostinger (para o DNS-01)

1. Painel Hostinger → **Perfil / API** → gere um **API token**.
2. Guarde o token — ele será usado pelo Caddy via variável de ambiente.

## 3. Instalar o Caddy COM o plugin da Hostinger

O binário padrão do Caddy não traz o provedor de DNS da Hostinger. Baixe um build
customizado em <https://caddyserver.com/download> marcando o módulo
`dns.providers.hostinger`, **ou** compile com `xcaddy`:

```powershell
# Requer Go instalado
go install github.com/caddyserver/xcaddy/cmd/xcaddy@latest
xcaddy build --with github.com/caddy-dns/hostinger
# Gera caddy.exe na pasta atual
```

Coloque o `caddy.exe` em algum lugar do PATH (ex.: `C:\caddy\caddy.exe`).

## 4. Abrir a porta 443 no roteador

Encaminhe **TCP 443** (porta externa) → IP da máquina, porta **443**.
Com DNS-01 a porta 80 **não** é necessária para o certificado (mas é útil se quiser
redirecionar HTTP→HTTPS; opcional).

Libere também a 443 no Firewall do Windows:

```powershell
New-NetFirewallRule -DisplayName "Caddy HTTPS" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow
```

## 5. Buildar o frontend de produção

O Caddy serve o build estático (não o `vite dev`):

```powershell
Set-Location C:\src\pics\frontend
npm install
npm run build   # gera C:\src\pics\frontend\dist
```

## 6. Backend

Continue rodando o uvicorn normalmente (HTTP, só local):

```powershell
Set-Location C:\src\pics\backend
& "C:\src\pics\backend\venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

> Pode usar `--host 127.0.0.1` já que só o Caddy (mesma máquina) acessa o backend.

No `backend/.env`, garanta que o domínio esteja liberado no CORS (útil para o app
mobile e para acesso direto em dev):

```
ALLOWED_HOSTS=localhost,127.0.0.1,pics.meulavoro.com.br
```

## 7. Rodar o Caddy

```powershell
# Define o token da Hostinger na sessão
$env:HOSTINGER_API_TOKEN = "SEU_TOKEN_AQUI"

Set-Location C:\src\pics
caddy run --config .\Caddyfile
```

Na primeira execução o Caddy cria o registro TXT `_acme-challenge` via API da
Hostinger, valida e emite o certificado. As renovações são automáticas.

### Rodar como serviço do Windows (opcional)

```powershell
$env:HOSTINGER_API_TOKEN = "SEU_TOKEN_AQUI"
caddy start --config C:\src\pics\Caddyfile
```

Para um serviço persistente que sobrevive a reboots, use o
[serviço oficial do Caddy para Windows](https://caddyserver.com/docs/running#windows-service)
e configure a variável `HOSTINGER_API_TOKEN` como variável de ambiente **do sistema**.

---

## O que mudou no código

- **Frontend** (`frontend/src/api.js`): em produção (atrás do proxy) a API usa
  `/api` na **mesma origem** — sem mixed-content e sem expor a 8000. Em dev
  (`:5173`) continua batendo direto no `:8000`.
- **App mobile** (`mobile/App.js`): base URL padrão agora é
  `https://pics.meulavoro.com.br`; URLs sem protocolo assumem `https://`.

## Impacto de performance

- Overhead de TLS é **desprezível**: handshake é custo único por conexão; com
  keep-alive + HTTP/2 (habilitado automaticamente pelo Caddy em HTTPS), o
  carregamento paralelo de thumbnails tende a **melhorar**.
- Servir fotos/vídeos é I/O-bound; a criptografia AES-NI não é gargalo.
