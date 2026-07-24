# install.ps1 — Instalador do PICS para novo Windows
# Requer: PowerShell 5+, Python 3.x no PATH, acesso à internet
# Uso: powershell -ExecutionPolicy Bypass -File install.ps1
#
# O que faz:
#   1. Verifica Python e pip
#   2. Cria venv e instala requirements.txt
#   3. Baixa e instala Caddy em C:\caddy\
#   4. Baixa ffmpeg (winget ou manual) e configura no .env
#   5. Cria/ajusta o .env com caminhos do novo PC
#   6. Gera start-backend.bat compatível
#   7. Instrui sobre cert SSL (opcional)

$ErrorActionPreference = 'Stop'
$ROOT = Split-Path $MyInvocation.MyCommand.Path

function Header($msg) {
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "  $msg" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
}

function Ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Info($msg) { Write-Host "  [..] $msg" -ForegroundColor Yellow }
function Err($msg)  { Write-Host "  [ERRO] $msg" -ForegroundColor Red }
function Ask($prompt, $default) {
    $ans = Read-Host "  $prompt [$default]"
    if ([string]::IsNullOrWhiteSpace($ans)) { return $default }
    return $ans.Trim()
}

# ─── 1. Python ────────────────────────────────────────────────────────────────
Header "1/7  Python"
$pyCmd = $null
foreach ($candidate in @('python', 'python3', 'py')) {
    try {
        $ver = & $candidate --version 2>&1
        if ($ver -match 'Python 3\.') { $pyCmd = $candidate; break }
    } catch {}
}
function Install-Python312 {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Err "winget nao encontrado. Instale Python 3.12 manualmente em https://www.python.org/downloads/"
        exit 1
    }
    Info "Instalando Python 3.12 via winget ..."
    winget install --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    # Recarrega PATH
    $env:PATH = [System.Environment]::GetEnvironmentVariable('PATH','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('PATH','User')
}

if (-not $pyCmd) {
    Info "Python 3 nao encontrado no PATH."
    Install-Python312
    # Tenta novamente apos instalar
    foreach ($candidate in @('py', 'python', 'python3')) {
        try {
            $ver = & $candidate --version 2>&1
            if ($ver -match 'Python 3\.') { $pyCmd = $candidate; break }
        } catch {}
    }
    if (-not $pyCmd) {
        Err "Python ainda nao encontrado. Feche e reabra o terminal e rode install.ps1 novamente."
        exit 1
    }
}

$pyVer = (& $pyCmd --version 2>&1).ToString().Trim()

# Verifica versao compativel (3.10-3.12 — numpy/insightface tem wheels prontas)
# pyArgs: argumentos extras para o interpretador (ex: -3.12 para py launcher)
$pyArgs = @()

if ($pyVer -match 'Python 3\.(1[3-9]|[2-9]\d)') {
    Info "$pyVer incompativel (numpy/insightface requerem 3.10-3.12). Instalando Python 3.12 ..."
    Install-Python312
    # Tenta py launcher com versao explicita
    try {
        $ver = & py -3.12 --version 2>&1
        if ($ver -match 'Python 3\.12') {
            $pyCmd  = 'py'
            $pyArgs = @('-3.12')
            $pyVer  = $ver.ToString().Trim()
        }
    } catch {}
    if ($pyArgs.Count -eq 0) {
        Err "Python 3.12 instalado mas nao encontrado. Feche e reabra o terminal e rode install.ps1 novamente."
        exit 1
    }
}
Ok "$pyVer encontrado"

# ─── 2. Venv + requirements ───────────────────────────────────────────────────
Header "2/7  Ambiente virtual Python (venv)"
$venvPath = Join-Path $ROOT "backend\venv"
$python   = Join-Path $venvPath "Scripts\python.exe"
$pip      = Join-Path $venvPath "Scripts\pip.exe"

# Verifica se o venv existente funciona neste PC (caminhos podem ser de outra maquina)
$venvOk = $false
if (Test-Path $python) {
    try {
        $testOut = & $python --version 2>&1
        if ($testOut -match 'Python 3\.') { $venvOk = $true }
    } catch {}
}

if (-not $venvOk) {
    if (Test-Path $venvPath) {
        Info "venv existente invalido (veio de outra maquina). Recriando ..."
        Remove-Item $venvPath -Recurse -Force
    } else {
        Info "Criando venv em $venvPath ..."
    }
    & $pyCmd @pyArgs -m venv $venvPath
    Ok "venv criado"
} else {
    Ok "venv ja existe e funciona"
}

Info "Atualizando pip ..."
& $python -m pip install --upgrade pip
Info "Instalando requirements.txt (pode demorar alguns minutos) ..."
& $pip install -r (Join-Path $ROOT "backend\requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Err "Falha ao instalar dependencias Python. Veja o erro acima."
    exit 1
}
Ok "Dependencias instaladas"

# ─── 3. Caddy ─────────────────────────────────────────────────────────────────
Header "3/7  Caddy (reverse proxy)"
$caddyDir = Join-Path $ROOT "tools\caddy"
$caddyExe = "$caddyDir\caddy.exe"

if (Test-Path $caddyExe) {
    $cv = (& $caddyExe version 2>&1).ToString().Trim()
    Ok "Caddy ja instalado: $cv"
} else {
    Info "Baixando Caddy v2 para $caddyDir ..."
    New-Item -ItemType Directory -Force -Path $caddyDir | Out-Null
    $caddyUrl = "https://github.com/caddyserver/caddy/releases/download/v2.9.1/caddy_2.9.1_windows_amd64.zip"
    $caddyZip = "$env:TEMP\caddy.zip"
    try {
        Invoke-WebRequest $caddyUrl -OutFile $caddyZip -UseBasicParsing
        Expand-Archive $caddyZip -DestinationPath $caddyDir -Force
        Remove-Item $caddyZip
        Ok "Caddy instalado em $caddyExe"
    } catch {
        Err "Falha ao baixar Caddy: $_"
        Err "Baixe manualmente em https://caddyserver.com/download e coloque o caddy.exe em tools\caddy\"
    }
}

# Cria pasta de certs
New-Item -ItemType Directory -Force -Path "$caddyDir\certs" | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $ROOT "tools\caddy\certs") | Out-Null

# ─── 4. FFmpeg ────────────────────────────────────────────────────────────────
Header "4/7  FFmpeg"
$ffmpegExe = $null
$ffprobeExe = $null

# Tenta encontrar ffmpeg já instalado
foreach ($candidate in @('ffmpeg', 'ffmpeg.exe')) {
    try {
        $null = & $candidate -version 2>&1
        $ffmpegExe = (Get-Command $candidate -ErrorAction SilentlyContinue).Source
        break
    } catch {}
}

if ($ffmpegExe) {
    $ffprobeExe = $ffmpegExe -replace 'ffmpeg\.exe','ffprobe.exe'
    if (-not (Test-Path $ffprobeExe)) { $ffprobeExe = $ffmpegExe -replace 'ffmpeg','ffprobe' }
    Ok "FFmpeg encontrado: $ffmpegExe"
} else {
    Info "FFmpeg nao encontrado. Tentando instalar via winget ..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        try {
            winget install --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements --silent 2>&1 | Out-Null
            # Procura o exe instalado
            $ffmpegSearch = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter 'ffmpeg.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($ffmpegSearch) {
                $ffmpegExe = $ffmpegSearch.FullName
                $ffprobeExe = Join-Path $ffmpegSearch.DirectoryName 'ffprobe.exe'
                Ok "FFmpeg instalado via winget: $ffmpegExe"
            }
        } catch {}
    }
    if (-not $ffmpegExe) {
        $ffmpegExe = Ask "Caminho completo do ffmpeg.exe" "C:\ffmpeg\bin\ffmpeg.exe"
        $ffprobeExe = Ask "Caminho completo do ffprobe.exe" ($ffmpegExe -replace 'ffmpeg\.exe','ffprobe.exe')
        if (-not (Test-Path $ffmpegExe)) {
            Err "ffmpeg.exe nao encontrado em $ffmpegExe"
            Err "Baixe em https://www.gyan.dev/ffmpeg/builds/ (ffmpeg-release-full.7z)"
            Err "Extraia e aponte o caminho. Edite o .env depois."
        }
    }
}

# ─── 5. .env ──────────────────────────────────────────────────────────────────
Header "5/7  Configuracao do .env"
$envFile = Join-Path $ROOT "backend\.env"
$envExample = Join-Path $ROOT "backend\.env.example"

if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Copy-Item $envExample $envFile
        Info ".env criado a partir do .env.example"
    } else {
        New-Item -ItemType File -Path $envFile | Out-Null
        Info ".env criado vazio"
    }
} else {
    Ok ".env ja existe — atualizando apenas caminhos de ffmpeg e database"
}

# Le o .env atual
$envLines = Get-Content $envFile

function SetEnvVar($lines, $key, $value) {
    $escaped = [regex]::Escape($key)
    $found = $false
    $result = $lines | ForEach-Object {
        if ($_ -match "^\s*$escaped\s*=") { $found = $true; "$key=$value" }
        else { $_ }
    }
    if (-not $found) { $result += "$key=$value" }
    return $result
}

# Ajusta caminhos absolutos que mudaram
$dbPath = Join-Path $ROOT "backend\pics.db" -Resolve 2>$null
if (-not $dbPath) { $dbPath = Join-Path $ROOT "backend\pics.db" }
$dbUrl  = "sqlite:///" + ($dbPath -replace '\\','/')

$envLines = SetEnvVar $envLines 'DATABASE_URL' $dbUrl

if ($ffmpegExe)  { $envLines = SetEnvVar $envLines 'FFMPEG_PATH'  ($ffmpegExe  -replace '\\','/') }
if ($ffprobeExe) { $envLines = SetEnvVar $envLines 'FFPROBE_PATH' ($ffprobeExe -replace '\\','/') }

# Pergunta sobre pastas de fonte e organizado
Write-Host ""
Info "Pastas de midia (deixe em branco para manter o valor atual do .env):"
$currentSource  = ($envLines | Where-Object { $_ -match '^SOURCE_DIR=' }  | Select-Object -First 1) -replace '^SOURCE_DIR=',''
$currentOrg     = ($envLines | Where-Object { $_ -match '^ORGANIZED_DIR=' } | Select-Object -First 1) -replace '^ORGANIZED_DIR=',''

$sourceDir = Ask "SOURCE_DIR (pasta onde ficam as fotos originais)" $currentSource
$orgDir    = Ask "ORGANIZED_DIR (pasta onde o app organiza as fotos)" $currentOrg

if ($sourceDir) { $envLines = SetEnvVar $envLines 'SOURCE_DIR' $sourceDir }
if ($orgDir)    { $envLines = SetEnvVar $envLines 'ORGANIZED_DIR' $orgDir }

# Frontend dist e portas
$envLines = SetEnvVar $envLines 'FRONTEND_PORT' '5173'
$envLines = SetEnvVar $envLines 'BACKEND_PORT'  '8000'

$envLines | Set-Content $envFile -Encoding UTF8
Ok ".env salvo em $envFile"

# ─── 6. Caddyfile — ajusta path do frontend dist ──────────────────────────────
Header "6/7  Caddyfile"
$caddyfile = Join-Path $ROOT "Caddyfile"
$distPath  = (Join-Path $ROOT "frontend\dist") -replace '/','\'

$caddyContent = Get-Content $caddyfile -Raw
$caddyContent = $caddyContent -replace 'root \* C:\\src\\pics\\frontend\\dist', "root * $distPath"
$caddyContent | Set-Content $caddyfile -Encoding UTF8 -NoNewline
Ok "Caddyfile atualizado com o caminho correto do frontend"

# ─── 7. Frontend build ────────────────────────────────────────────────────────
Header "7/7  Frontend (build de producao)"
$frontendDist = Join-Path $ROOT "frontend\dist"
if (Test-Path (Join-Path $frontendDist "index.html")) {
    Ok "Build do frontend ja existe — pulando"
} else {
    # Garante Node.js / npm disponivel
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) {
        Info "npm nao encontrado. Instalando Node.js LTS via winget ..."
        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if ($winget) {
            winget install --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements 2>&1 | Out-Null
            # Recarrega PATH da sessao
            $env:PATH = [System.Environment]::GetEnvironmentVariable('PATH','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('PATH','User')
            $npm = Get-Command npm -ErrorAction SilentlyContinue
        }
        if (-not $npm) {
            Err "Nao foi possivel instalar Node.js automaticamente."
            Err "Instale manualmente em https://nodejs.org/ e execute novamente install.ps1"
            exit 1
        }
        Ok "Node.js instalado: $(node --version)"
    }

    Info "Rodando npm install + npm run build ..."
    Push-Location (Join-Path $ROOT "frontend")
    npm install --silent 2>&1 | Out-Null
    npm run build 2>&1
    Pop-Location
    Ok "Frontend buildado"
}

# ─── Resumo ───────────────────────────────────────────────────────────────────
Header "Instalacao concluida"
$backendCmd = "cd $ROOT\backend ; venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
$caddyCmd   = "$ROOT\tools\caddy\caddy.exe run --config $ROOT\Caddyfile"
$startCmd   = "$ROOT\start.bat"
Write-Host ""
Write-Host "  Para rodar o PICS:" -ForegroundColor White
Write-Host "    start.bat  (pergunta modo dev ou prod)" -ForegroundColor Green
Write-Host ""
Write-Host "  Ou manualmente:" -ForegroundColor White
Write-Host "    Backend : $backendCmd" -ForegroundColor Gray
Write-Host "    Caddy   : $caddyCmd" -ForegroundColor Gray
Write-Host ""
Write-Host "  Acesso HTTP (sem SSL) : http://localhost:8080" -ForegroundColor White
Write-Host "  Acesso HTTPS          : https://<dominio>:8443 (requer cert em tools\caddy\certs\)" -ForegroundColor White
Write-Host ""
Write-Host "  SSL    : $ROOT\SSL_SETUP.md" -ForegroundColor Gray
Write-Host "  rclone : $ROOT\backend\RCLONE_GUIDE.md" -ForegroundColor Gray
Write-Host ""
