# PICS — Guia de Deploy (novo PC)

## Pré-requisitos
- Windows 10/11
- PowerShell 7 (pwsh): `winget install --id Microsoft.PowerShell --accept-package-agreements`
- Git: `winget install --id Git.Git --accept-package-agreements`
- Acesso à internet (install.ps1 baixa Python 3.12, Node.js, Caddy, ffmpeg se necessário)

---

## 1. Clonar o repositório

```cmd
git clone https://github.com/klaused-spec/pics.git C:\src\pics
cd C:\src\pics
```

---

## 2. Executar o instalador

```powershell
pwsh -ExecutionPolicy Bypass -File install.ps1
```

O instalador faz automaticamente:
- Verifica/instala Python 3.12 (numpy/insightface requerem 3.10–3.12)
- Cria `backend\venv` e instala `requirements.txt`
- Baixa Caddy em `tools\caddy\caddy.exe`
- Detecta/instala ffmpeg via winget
- Cria/atualiza `backend\.env` com caminhos do PC atual
- Instala Node.js se ausente e gera build do frontend (`frontend\dist`)

---

## 3. Restaurar arquivos sensíveis

Extraia o arquivo `pics-sensitive.zip` na raiz do projeto (`C:\src\pics`):

```powershell
Expand-Archive pics-sensitive.zip -DestinationPath C:\src\pics -Force
```

Arquivos restaurados:
| Arquivo | Descrição |
|---|---|
| `backend\.env` | Configurações e segredos do backend |
| `backend\pics.db` | Banco de dados SQLite com toda a biblioteca |
| `tools\caddy\certs\fullchain.pem` | Certificado SSL |
| `tools\caddy\certs\privkey.pem` | Chave privada SSL |
| `tools\rclone\rclone.conf` | Configuração rclone (tokens OneDrive) |

> **Atenção:** após restaurar o `.env`, verifique se os caminhos `SOURCE_DIR`, `ORGANIZED_DIR`, `DATABASE_URL`, `FFMPEG_PATH` e `FFPROBE_PATH` correspondem ao novo PC. O `install.ps1` ajusta esses caminhos automaticamente se rodado depois.

---

## 4. Abrir portas no firewall (se necessário)

```cmd
netsh advfirewall firewall add rule name="PICS Backend" dir=in action=allow protocol=TCP localport=8000
netsh advfirewall firewall add rule name="PICS Caddy HTTP" dir=in action=allow protocol=TCP localport=8080
netsh advfirewall firewall add rule name="PICS Caddy HTTPS" dir=in action=allow protocol=TCP localport=8443
```

---

## 5. Iniciar

```cmd
cd C:\src\pics
start.bat
```

Escolha o modo:
- **dev** — backend (`:8000`) + Vite frontend (`:5173`). Requer Node.js.
- **prod** — backend (`:8000`) + Caddy HTTP (`:8080`) + Caddy HTTPS (`:8443`).

### Acesso
| Modo | URL |
|---|---|
| HTTP local | `http://localhost:8080` |
| HTTPS (domínio) | `https://pics.meulavoro.com.br:8443` |
| App mobile | `https://pics.meulavoro.com.br:8443` nas settings |

---

## 6. App mobile (APK)

O APK mais recente está disponível nos [Releases do GitHub](https://github.com/klaused-spec/pics/releases).

Instale no Android com "Instalar de fontes desconhecidas" ativado.  
Após instalar, configure o servidor nas settings do app:
```
https://pics.meulavoro.com.br:8443
```

---

## Notas

- O `backend\venv` **não é portátil** entre PCs. Se copiado de outro PC, o `install.ps1` detecta e recria automaticamente.
- Os certs SSL vencem periodicamente. Para renovar: `pwsh -File issue-cert.ps1` (requer acesso à Hostinger).
- rclone: se o token OneDrive expirar, reconecte com `rclone config reconnect onedrive-klauskirner:`.
- Logs do backend: `backend\logs\`.
