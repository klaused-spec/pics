# export-sensitive.ps1 — Exporta arquivos sensiveis para pics-sensitive.zip
# Uso: pwsh -ExecutionPolicy Bypass -File export-sensitive.ps1
# Ou:  powershell -ExecutionPolicy Bypass -File export-sensitive.ps1

$ROOT = Split-Path $MyInvocation.MyCommand.Path
$OUT  = Join-Path $ROOT "pics-sensitive.zip"

$files = @(
    "backend\.env",
    "backend\pics.db",
    "tools\caddy\certs\fullchain.pem",
    "tools\caddy\certs\privkey.pem",
    "tools\rclone\rclone.conf",
    "backend\models\1k3d68.onnx",
    "backend\models\2d106det.onnx",
    "backend\models\det_10g.onnx",
    "backend\models\genderage.onnx",
    "backend\models\w600k_r50.onnx"
)

Write-Host "`nExportando arquivos sensiveis..." -ForegroundColor Cyan

if (Test-Path $OUT) { Remove-Item $OUT }

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::Open($OUT, 'Create')

foreach ($rel in $files) {
    $full = Join-Path $ROOT $rel
    if (Test-Path $full) {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $full, $rel, 'Optimal') | Out-Null
        Write-Host "  [OK] $rel" -ForegroundColor Green
    } else {
        Write-Host "  [--] AUSENTE: $rel" -ForegroundColor Yellow
    }
}

$zip.Dispose()

$size = [math]::Round((Get-Item $OUT).Length / 1MB, 1)
Write-Host "`nGerado: $OUT ($size MB)" -ForegroundColor Cyan
Write-Host "Guarde este arquivo em local seguro (pendrive, nuvem privada)." -ForegroundColor Gray
