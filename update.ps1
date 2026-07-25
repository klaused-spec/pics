param(
    [switch]$NoBuild,
    [switch]$RestartBackend,
    [switch]$DownloadApk,
    [string]$GithubToken = $env:GITHUB_TOKEN
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

# 3. Baixar APK mais recente do GitHub Actions (aguarda build se necessário)
if ($DownloadApk) {
    Write-Host "`n[3/4] APK do GitHub Actions..." -ForegroundColor Yellow
    $ProgressPreference = 'SilentlyContinue'
    $repo = 'klaused-spec/pics'
    $artifactName = 'pics-mobile-release-apk'
    $destDir = "$Root\mobile\pics-mobile-debug-apk"

    try {
        $ghToken = if ($GithubToken) { $GithubToken } else { $env:GITHUB_TOKEN }
        if (-not $ghToken) { throw 'Token nao encontrado. Defina GITHUB_TOKEN no ambiente ou use -GithubToken <PAT>' }

        $headers = @{
            Authorization          = "Bearer $ghToken"
            Accept                 = 'application/vnd.github+json'
            'X-GitHub-Api-Version' = '2022-11-28'
            'User-Agent'           = 'pics-update'
        }

        # Aguarda a run mais recente terminar (polling a cada 30s, max 20 min)
        $maxWait = 20 * 60
        $waited = 0
        $run = $null
        while ($true) {
            $runs = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/actions/workflows/android-apk.yml/runs?per_page=1" -Headers $headers
            $run = $runs.workflow_runs[0]
            if (-not $run) { throw 'Nenhuma run encontrada' }

            if ($run.status -eq 'completed') {
                Write-Host ("  Run #{0} concluida: {1}" -f $run.run_number, $run.conclusion)
                break
            }

            if ($waited -ge $maxWait) { throw "Timeout aguardando build (>20 min)" }
            Write-Host ("  Run #{0} ainda em andamento (status={1})... aguardando 30s [{2}s/{3}s]" -f $run.run_number, $run.status, $waited, $maxWait)
            Start-Sleep -Seconds 30
            $waited += 30
        }

        if ($run.conclusion -ne 'success') { throw "Build falhou (conclusion=$($run.conclusion)). Veja os logs do GitHub Actions." }

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
        Write-Host "  ERRO no download do APK: $_" -ForegroundColor Red
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
