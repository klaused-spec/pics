## 🚀 DEPLOYMENT DO PICS COM SEGURANÇA

### 1️⃣ Preparação do Backend

```bash
cd backend

# Copiar .env.example para .env
cp .env.example .env

# Editar .env com suas configurações
nano .env
# Importante:
# - Gerar SECRET_KEY: python -c "import secrets; print(secrets.token_urlsafe(32))"
# - Atualizar ALLOWED_HOSTS com seu domínio: klaused.tplinkdns.com
```

### 2️⃣ Configurações Críticas do `.env`

```env
# ===== AUTENTICAÇÃO JWT =====
SECRET_KEY=gerar-com-secrets.token_urlsafe(32)
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# ===== FRONTEND - CORS =====
ALLOWED_HOSTS=localhost,127.0.0.1,klaused.tplinkdns.com
FRONTEND_PORT=5173
BACKEND_PORT=8000

# ===== BANCO DE DADOS =====
DATABASE_URL=sqlite:///./pics.db

# ===== SERVIDOR =====
HOST=0.0.0.0
PORT=8000

# ===== AZURE OPENAI (se usar IA) =====
AZURE_OPENAI_ENDPOINT=https://seu-recurso.openai.azure.com/
AZURE_OPENAI_KEY=sua-chave
```

### 3️⃣ Iniciar Backend (em Produção)

#### Opção A: Com Uvicorn (simples)
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload=False
```

#### Opção B: Com Gunicorn (recomendado)
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 --timeout 120 app.main:app
```

#### Opção C: Com Docker
```bash
docker build -t pics-backend .
docker run -p 8000:8000 -v $(pwd):/app --env-file .env pics-backend
```

### 4️⃣ Preparação do Frontend

```bash
cd frontend

# Instalar dependências
npm install

# Build para produção
npm run build
```

### 5️⃣ Acessar a App

Depois que backend e frontend estão rodando:

```
Frontend: http://klaused.tplinkdns.com:5173
Backend API: http://klaused.tplinkdns.com:8000/api
```

### 6️⃣ Fluxo de Login

1. Usuário vai para http://klaused.tplinkdns.com:5173
2. Clica em "Registrar" ou "Login"
3. Frontend envia credenciais para `POST /api/auth/login` ou `/api/auth/register`
4. Backend retorna JWT token
5. Frontend armazena token em localStorage
6. Todas as requisições posteriores incluem o token automaticamente

### 7️⃣ Port Forwarding (Router TP-Link)

Você precisa expor 2 portas na internet:

**Na router (TP-Link):**
1. Port Forwarding → External Port 5173 → Internal Port 5173
2. Port Forwarding → External Port 8000 → Internal Port 8000

Ou use **Cloudflare Tunnel** (recomendado - mais seguro):
```bash
pip install cloudflare-tunnel
# Ou configure no dashboard do Cloudflare
```

### 8️⃣ HTTPS em Produção (OBRIGATÓRIO)

Para expor na internet, SEMPRE use HTTPS:

#### Opção A: Let's Encrypt + Nginx
```bash
sudo certbot certonly --standalone -d klaused.tplinkdns.com
# Depois configure Nginx como reverse proxy
```

#### Opção B: Cloudflare Tunnel (grátis + HTTPS automático)
```bash
# Cloudflare Tunnel oferece HTTPS automático sem precisar de certificado
```

---

## 🔐 Checklist de Segurança Antes de Expor

- [ ] `SECRET_KEY` é uma string aleatória segura (32+ chars)
- [ ] `ALLOWED_HOSTS` contém seu domínio correto
- [ ] `DATABASE_URL` aponta para um arquivo com permissões restritas
- [ ] HTTPS está habilitado (não expor HTTP)
- [ ] Senhas dos usuários são fortes
- [ ] Backup do banco de dados é feito regularmente
- [ ] Rate limiting está ativo (contra brute force)
- [ ] CORS está restritivo (não allow_origins ["*"])

---

## 📊 Monitoramento

### Ver logs do backend:
```bash
tail -f logs/app.log
```

### Ver jobs em execução:
```bash
curl -H "Authorization: Bearer {token}" \
  http://klaused.tplinkdns.com:8000/api/jobs/
```

---

## 🛠️ Troubleshooting

### "Token inválido" ao fazer request
- Verificar se token está no localStorage
- Verificar se SECRET_KEY é a mesma entre restarts
- Verificar se token não expirou (24h por padrão)

### CORS error no frontend
- Verificar se ALLOWED_HOSTS contém o domínio
- Verificar se `Access-Control-Allow-Credentials: true` está ativo
- Limpar cache do browser

### Backend não inicia
- Verificar `.env` tem todas as variáveis necessárias
- Verificar permissões de escrita na pasta
- Verificar se porta 8000 não está em uso: `netstat -an | grep 8000`

