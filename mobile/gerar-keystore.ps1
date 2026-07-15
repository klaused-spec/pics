# Gera a keystore de UPLOAD para assinar o app Android e prepara o base64
# para colar como GitHub Secret. Execute VOCE mesmo (as senhas sao digitadas
# por voce no terminal e NAO passam por lugar nenhum automatizado).
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File .\mobile\gerar-keystore.ps1
#
# Ao final voce tera:
#   - <perfil>\pics-upload-key.jks  (GUARDE em cofre; esta no .gitignore)
#   - o conteudo base64 copiado para a area de transferencia (Set-Clipboard)
#
# Depois, cadastre em GitHub > Settings > Secrets and variables > Actions:
#   ANDROID_KEYSTORE_BASE64   = (o base64 copiado)
#   ANDROID_KEYSTORE_PASSWORD = a senha da keystore que voce digitou
#   ANDROID_KEY_ALIAS         = pics-upload
#   ANDROID_KEY_PASSWORD      = a senha da key que voce digitou

$ErrorActionPreference = 'Stop'

# Localiza o keytool (JDK/JRE instalado)
$keytool = Get-Command keytool -ErrorAction SilentlyContinue
if (-not $keytool) {
    $candidatos = @(
        'C:\Program Files\Java\jre-1.8\bin\keytool.exe',
        'C:\Program Files\Java\*\bin\keytool.exe',
        'C:\Program Files (x86)\Java\*\bin\keytool.exe'
    )
    foreach ($c in $candidatos) {
        $found = Get-ChildItem $c -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { $keytool = $found.FullName; break }
    }
} else {
    $keytool = $keytool.Source
}

if (-not $keytool) {
    Write-Error "keytool nao encontrado. Instale um JDK (ex.: Temurin 17) e rode de novo."
    exit 1
}
Write-Host "keytool: $keytool" -ForegroundColor Cyan

$ksPath = Join-Path $env:USERPROFILE 'pics-upload-key.jks'
if (Test-Path $ksPath) {
    Write-Warning "Ja existe uma keystore em $ksPath. Se sobrescrever, PERDERA a chave anterior."
    $resp = Read-Host "Digite SIM para sobrescrever, ou ENTER para cancelar"
    if ($resp -ne 'SIM') { Write-Host 'Cancelado.'; exit 0 }
    Remove-Item $ksPath -Force
}

$alias = 'pics-upload'
Write-Host "`nGerando keystore. Responda as perguntas do keytool (senha, nome, etc.)." -ForegroundColor Yellow
Write-Host "IMPORTANTE: anote a senha da keystore e a senha da key em um cofre.`n" -ForegroundColor Yellow

& $keytool -genkeypair -v `
    -keystore $ksPath `
    -alias $alias `
    -keyalg RSA -keysize 2048 -validity 10000 `
    -storetype JKS

if ($LASTEXITCODE -ne 0 -or -not (Test-Path $ksPath)) {
    Write-Error "Falha ao gerar a keystore."
    exit 1
}

Write-Host "`nKeystore criada: $ksPath" -ForegroundColor Green

# Gera base64 e copia para a area de transferencia
$b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($ksPath))
try {
    $b64 | Set-Clipboard
    Write-Host "Base64 da keystore copiado para a area de transferencia." -ForegroundColor Green
} catch {
    $outFile = Join-Path $env:USERPROFILE 'pics-upload-key.b64.txt'
    $b64 | Set-Content -Path $outFile -Encoding ASCII
    Write-Host "Nao foi possivel copiar; base64 salvo em: $outFile" -ForegroundColor Yellow
}

Write-Host "`n=== PROXIMOS PASSOS ===" -ForegroundColor Cyan
Write-Host "1. GitHub > Settings > Secrets and variables > Actions > New repository secret:" -ForegroundColor White
Write-Host "     ANDROID_KEYSTORE_BASE64   = (Ctrl+V; ja esta copiado)"
Write-Host "     ANDROID_KEYSTORE_PASSWORD = a senha da keystore que voce digitou"
Write-Host "     ANDROID_KEY_ALIAS         = $alias"
Write-Host "     ANDROID_KEY_PASSWORD      = a senha da key que voce digitou"
Write-Host "2. Actions > 'Android AAB (Play Store)' > Run workflow (para gerar o .aab assinado)." -ForegroundColor White
Write-Host "3. GUARDE $ksPath em um cofre. Sem ele voce nao atualiza o app publicado." -ForegroundColor White
