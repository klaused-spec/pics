# Guia — rclone OneDrive (integrado ao pics)

O download de contas OneDrive foi **incorporado ao pics** (antes era o projeto
standalone `C:\src\rclone_onedrivesync`). A lógica vive em
`backend/app/services/rclone_sync.py` e roda como um job em background.

- **Ativar:** `RCLONE_ENABLED=true` no `backend/.env` (e reiniciar o backend).
- **Rodar manual:** botão "Baixar do OneDrive" na página de Manutenção, ou
  `POST /api/jobs/rclone-download`.
- **Automático:** agendado a cada `RCLONE_INTERVAL_MINUTES` (padrão 60) quando
  `RCLONE_ENABLED=true`.
- **Dedup:** não baixa arquivos cujo NOME já existe na biblioteca (consulta o
  banco) + `--ignore-existing` no destino.

O rclone usa o config global do sistema:
`C:\Users\<user>\AppData\Roaming\rclone\rclone.conf`.

---

## Pré-requisitos

- **rclone** instalado: `winget install Rclone.Rclone`

---

## Configuração no `backend/.env`

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `RCLONE_ENABLED` | `false` | Liga/desliga a integração |
| `RCLONE_PATH` | `rclone` | Caminho do executável |
| `RCLONE_TRANSFERS` | `8` | Downloads paralelos |
| `RCLONE_CHECKERS` | `16` | Verificações paralelas |
| `RCLONE_INTERVAL_MINUTES` | `60` | Intervalo do job automático |
| `RCLONE_DEST_DIR` | vazio | Destino (vazio = `SOURCE_DIR`) |
| `RCLONE_MULTI_THREAD_STREAMS` | `0` | Streams multi-thread (0 = rclone decide) |
| `RCLONE_BUFFER_SIZE` | `256M` | Buffer por transferência |
| `RCLONE_ONEDRIVE_CHUNK_SIZE` | `10M` | Tamanho do chunk OneDrive |
| `RCLONE_STATS_INTERVAL` | `10s` | Intervalo dos stats (progresso) |
| `RCLONE_LOG_LEVEL` | `INFO` | Verbosidade do log |
| `RCLONE_REMOTES_RAW` | vazio | Perfis em JSON (ver abaixo) |

### Perfis (`RCLONE_REMOTES_RAW`)

JSON com uma lista de objetos `{name, remote, folders}`. `folders` vazio =
conta inteira. Cada `name` vira uma subpasta no destino.

```
RCLONE_REMOTES_RAW=[{"name":"klauskirner","remote":"onedrive-klauskirner","folders":["Imagens","Pictures"]}]
```

Para várias contas:

```
RCLONE_REMOTES_RAW=[{"name":"klauskirner","remote":"onedrive-klauskirner","folders":["Imagens","Pictures"]},{"name":"familiaklin01","remote":"onedrive-familiaklin01","folders":[]}]
```

---

## Como adicionar uma nova conta OneDrive

### Passo 1 — Gerar o token OAuth

```powershell
rclone authorize "onedrive"
```

Abre o browser; faça login com a conta desejada. Ao final o terminal exibe um
JSON com `access_token` e `refresh_token`. Copie tudo.

### Passo 2 — Obter o drive_id

```powershell
$token = "COLE_O_ACCESS_TOKEN_AQUI"
$r = Invoke-RestMethod -Uri "https://graph.microsoft.com/v1.0/me/drive" `
     -Headers @{Authorization="Bearer $token"}
"drive_id: $($r.id)  |  type: $($r.driveType)"
```

### Passo 3 — Adicionar ao rclone.conf global

Abra `%APPDATA%\rclone\rclone.conf` e adicione:

```ini
[onedrive-NOME]
type = onedrive
token = {"access_token":"...","token_type":"Bearer","refresh_token":"...","expiry":"..."}
drive_id = DRIVE_ID_AQUI
drive_type = personal
```

### Passo 4 — Adicionar ao `RCLONE_REMOTES_RAW` no `.env` e reiniciar o backend

### Passo 5 — Testar

```powershell
rclone lsd onedrive-NOME:
```

Depois use o botão "Baixar do OneDrive" na página de Manutenção.

---

## Renovar token expirado

O `refresh_token` renova o `access_token` automaticamente. Se falhar, repita os
passos 1-3 para a conta, atualizando o bloco no `rclone.conf`.
