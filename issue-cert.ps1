# issue-cert.ps1
# Emite (ou renova) o certificado Let's Encrypt para pics.meulavoro.com.br
# usando DNS-01 MANUAL. O certbot vai PAUSAR e pedir para voce criar um
# registro TXT no painel DNS da Hostinger. Apos criar e propagar, pressione
# Enter no terminal para continuar.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File .\issue-cert.ps1
#
# Requisitos: certbot instalado (ja feito via pip).

$ErrorActionPreference = 'Stop'

$Domain     = 'pics.meulavoro.com.br'
$Email      = 'klaused@gmail.com'
$Certbot    = 'C:\Users\Admin\AppData\Roaming\Python\Python312\Scripts\certbot.exe'
$CertbotDir = 'C:\caddy\certbot'         # config/work/logs do certbot
$CaddyCerts = 'C:\caddy\certs'           # onde o Caddy le o cert (ver Caddyfile)

if (-not (Test-Path $Certbot)) {
	Write-Error "certbot nao encontrado em $Certbot. Instale com: python -m pip install --user certbot"
}

New-Item -ItemType Directory -Force -Path $CertbotDir | Out-Null
New-Item -ItemType Directory -Force -Path $CaddyCerts | Out-Null

Write-Host "==> Emitindo certificado para $Domain (DNS-01 manual)..." -ForegroundColor Cyan
Write-Host "    O certbot vai mostrar um valor TXT. Crie no painel Hostinger:" -ForegroundColor Yellow
Write-Host "      Tipo: TXT" -ForegroundColor Yellow
Write-Host "      Nome: _acme-challenge.pics   (host relativo ao dominio meulavoro.com.br)" -ForegroundColor Yellow
Write-Host "      Valor: (o que o certbot exibir)" -ForegroundColor Yellow
Write-Host "    Aguarde ~1-2 min de propagacao e so entao pressione Enter no certbot." -ForegroundColor Yellow
Write-Host ""

& $Certbot certonly `
	--manual `
	--preferred-challenges dns `
	--config-dir  $CertbotDir `
	--work-dir    (Join-Path $CertbotDir 'work') `
	--logs-dir    (Join-Path $CertbotDir 'logs') `
	--agree-tos `
	--email       $Email `
	--no-eff-email `
	-d            $Domain

if ($LASTEXITCODE -ne 0) {
	Write-Error "certbot falhou (exit $LASTEXITCODE)."
}

$live = Join-Path $CertbotDir "live\$Domain"
Copy-Item (Join-Path $live 'fullchain.pem') (Join-Path $CaddyCerts 'fullchain.pem') -Force
Copy-Item (Join-Path $live 'privkey.pem')   (Join-Path $CaddyCerts 'privkey.pem')   -Force

Write-Host ""
Write-Host "==> Certificado copiado para $CaddyCerts" -ForegroundColor Green
Write-Host "    Reinicie o Caddy para carregar: caddy reload --config C:\src\pics\Caddyfile" -ForegroundColor Green
Write-Host ""
Write-Host "OBS: como e DNS-01 MANUAL, a renovacao (a cada ~60-90 dias) tambem sera" -ForegroundColor DarkYellow
Write-Host "     manual: rode este script de novo e crie o novo TXT quando pedir." -ForegroundColor DarkYellow
