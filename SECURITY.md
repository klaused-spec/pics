## 🔐 SEGURANÇA IMPLEMENTADA NO PICS

### ✅ Autenticação JWT

#### Endpoints de Autenticação:
- `POST /api/auth/register` - Registrar novo usuário
- `POST /api/auth/login` - Login com email/senha
- `GET /api/auth/me` - Obter usuário atual (requer token)

#### Fluxo:
1. Usuário faz login → recebe `access_token`
2. Frontend armazena token em `localStorage`
3. Frontend envia token em cada requisição: `Authorization: Bearer {token}`
4. Backend valida token antes de processar

---

### 🛡️ Proteção de Rotas

Todas as rotas foram protegidas com autenticação JWT obrigatória:

#### `/api/media/*` - Mídia
- `GET /media/` - Listar mídias ✅
- `GET /media/search` - Buscar ✅
- `GET /media/timeline` - Timeline ✅
- `GET /media/stats` - Estatísticas ✅
- `GET /media/duplicates` - Listar duplicatas ✅
- `DELETE /media/duplicates/all` - Apagar duplicatas ✅
- `GET /media/{id}` - Obter mídia ✅
- `GET /media/{id}/file` - Download ✅
- `GET /media/{id}/thumbnail` - Thumbnail ✅
- `GET /media/{id}/stream` - Stream vídeo ✅
- `DELETE /media/{id}` - Deletar mídia ✅

#### `/api/persons/*` - Pessoas & Rostos
- `GET /persons/` - Listar pessoas ✅
- `POST /persons/` - Criar pessoa ✅
- `PUT /persons/{id}` - Atualizar pessoa ✅
- `DELETE /persons/{id}` - Deletar pessoa ✅
- `GET /persons/{id}/media` - Mídias da pessoa ✅
- `POST /persons/faces/{id}/assign` - Atribuir rosto ✅
- `POST /persons/merge` - Mesclar pessoas ✅
- `POST /persons/cluster` - Clustering de rostos ✅

#### `/api/jobs/*` - Processamento
- `GET /jobs/` - Listar jobs ✅
- `POST /jobs/scan` - Iniciar scan ✅
- `POST /jobs/ai-process` - Processamento IA ✅
- `POST /jobs/face-detect` - Detecção facial ✅
- `POST /jobs/full-pipeline` - Pipeline completo ✅
- `POST /jobs/sync` - Sincronizar ✅
- `GET /jobs/audit` - Auditoria ✅

#### `/api/albums/*` - Álbuns
- `GET /albums/` - Listar álbuns ✅
- `POST /albums/` - Criar álbum ✅

#### `/api/settings/*` - Configurações
- `GET /settings/paths` - Obter paths ✅
- `GET /settings/backup` - Backup ✅
- `POST /settings/restore` - Restore ✅

---

### 🌐 CORS Dinâmico

O CORS agora é configurado dinamicamente via `.env`:

```env
ALLOWED_HOSTS=localhost,127.0.0.1,klaused.tplinkdns.com
FRONTEND_PORT=5173
BACKEND_PORT=8000
```

Aceita automaticamente:
- HTTP e HTTPS para cada host
- Qualquer IP local (192.168.x.x, 172.x.x.x, etc.)
- Domínios configurados no `.env`

---

### 📝 Configurações Obrigatórias

No `.env`, certifique-se de ter:

```env
# ===== AUTENTICAÇÃO JWT =====
SECRET_KEY=gerar-chave-segura-32-chars-min
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# ===== FRONTEND - CORS =====
ALLOWED_HOSTS=localhost,127.0.0.1,klaused.tplinkdns.com
FRONTEND_PORT=5173
BACKEND_PORT=8000
```

**Para gerar SECRET_KEY segura:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

### 🚀 Como Usar no Frontend

#### 1. Registrar usuário:
```javascript
import { register } from '@/api'

const response = await register('user@example.com', 'senha123')
localStorage.setItem('access_token', response.data.access_token)
localStorage.setItem('user', JSON.stringify(response.data.user))
```

#### 2. Login:
```javascript
import { login } from '@/api'

const response = await login('user@example.com', 'senha123')
localStorage.setItem('access_token', response.data.access_token)
localStorage.setItem('user', JSON.stringify(response.data.user))
```

#### 3. Usar API protegida (token é automaticamente adicionado):
```javascript
import { getMedia } from '@/api'

// Token é automaticamente incluído no header
const response = await getMedia({ page: 1 })
```

#### 4. Logout:
```javascript
import { logout } from '@/api'

logout() // Remove token do localStorage
```

---

### 🔑 Segurança em Produção

Para produção, **OBRIGATÓRIO**:

1. **Alterar SECRET_KEY** em `.env` para uma chave segura aleatória
2. **Usar HTTPS** em vez de HTTP
3. **Rate limiting** nas rotas de login para prevenir brute force
4. **Senhas fortes** para o primeiro usuário
5. **Backups** regulares do banco de dados

---

### ⚠️ Endpoints Públicos (SEM Autenticação)

Apenas estes 3 endpoints NÃO requerem autenticação:
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/health`

Tudo mais requer token JWT válido!

