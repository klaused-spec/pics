param(
    [switch]$NoBuild,
    [switch]$RestartBackend,
    [switch]$DownloadApk
)

$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $Root

Write-Host "=== PICS Update ===" -ForegroundColor Cyan

# 1. Git pull
Write-Host "`n[1/4] Git pull..." -ForegroundColor Yellow
git pull
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: git pull falhou." -ForegroundColor Red
    exit 1
}

# 2. Build frontend
if (-not $NoBuild) {
    Write-Host "`n[2/4] Build do frontend..." -ForegroundColor Yellow
    Set-Location "$Root\frontend"
    npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERRO: build falhou." -ForegroundColor Red
        exit 1
    }
    Set-Location $Root
    Write-Host "Build concluido." -ForegroundColor Green
} else {
    Write-Host "`n[2/4] Build ignorado (-NoBuild)." -ForegroundColor Gray
}

# 3. Baixar APK mais recente do GitHub Actions
if ($DownloadApk) {
    Write-Host "`n[3/4] Baixando APK do GitHub Actions..." -ForegroundColor Yellow
    $ProgressPreference = 'SilentlyContinue'
    $repo = 'klaused-spec/pics'
    $artifactName = 'pics-mobile-release-apk'
    $destDir = "$Root\mobile\pics-mobile-debug-apk"

    try {
        $credText = "protocol=https`nhost=github.com`n`n"
        $cred = $credText | git credential fill
        $ghToken = ($cred -split "`n" | Where-Object { $_ -like 'password=*' }) -replace '^password=', ''
        if (-not $ghToken) { throw 'Nao consegui obter o token do git credential' }

        $headers = @{
            Authorization          = "Bearer $ghToken"
            Accept                 = 'application/vnd.github+json'
            'X-GitHub-Api-Version' = '2022-11-28'
            'User-Agent'           = 'pics-update'
        }

        $runs = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/actions/workflows/android-apk.yml/runs?per_page=1" -Headers $headers
        $run = $runs.workflow_runs[0]
        if (-not $run) { throw 'Nenhuma run encontrada' }
        Write-Host ("  Run #{0} status={1} conclusion={2}" -f $run.run_number, $run.status, $run.conclusion)

        if ($run.status -ne 'completed') { throw "Run ainda nao terminou (status=$($run.status)). Aguarde o build e rode de novo." }
        if ($run.conclusion -ne 'success') { throw "Run falhou (conclusion=$($run.conclusion)). Veja os logs do GitHub Actions." }

        $arts = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/actions/runs/$($run.id)/artifacts" -Headers $headers
        $art = $arts.artifacts | Where-Object { $_.name -eq $artifactName } | Select-Object -First 1
        if (-not $art) { throw "Artifact '$artifactName' nao encontrado." }

        New-Item -ItemType Directory -Force -Path $destDir | Out-Null
        $zipPath = Join-Path $destDir '_apk.zip'

        Write-Host ("  Baixando {0:N1} MB..." -f ($art.size_in_bytes / 1MB))
        $wc = New-Object System.Net.WebClient
        $wc.Headers.Add('Authorization', "Bearer $ghToken")
        $wc.Headers.Add('User-Agent', 'pics-update')
        $wc.DownloadFile($art.archive_download_url, $zipPath)
        $wc.Dispose()

        Expand-Archive -Path $zipPath -DestinationPath $destDir -Force
        Remove-Item $zipPath -Force

        $apk = Get-ChildItem -Path $destDir -Filter *.apk | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        Write-Host ("  APK salvo: {0} ({1:N1} MB)" -f $apk.FullName, ($apk.Length / 1MB)) -ForegroundColor Green
    } catch {
        Write-Host "  AVISO: download do APK falhou: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "`n[3/4] APK ignorado (use -DownloadApk para baixar)." -ForegroundColor Gray
}

# 4. Reiniciar backend (opcional)
if ($RestartBackend) {
    Write-Host "`n[4/4] Reiniciando backend..." -ForegroundColor Yellow
    cmd /c "$Root\restart-app.bat"
} else {
    Write-Host "`n[4/4] Backend NAO reiniciado (use -RestartBackend para reiniciar)." -ForegroundColor Gray
}

Write-Host "`n=== Concluido ===" -ForegroundColor Cyan
