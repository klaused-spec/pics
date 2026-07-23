param([int]$SkipPid = 0)
# Aguarda resposta HTTP chegar ao cliente antes de matar tudo.
Start-Sleep -Seconds 2

# Mata caddy primeiro (nao mata a si mesmo).
Get-Process -Name caddy -ErrorAction SilentlyContinue | Stop-Process -Force

# Mata todos os python.exe exceto o proprio processo de restart (se aplicavel).
Get-Process -Name python -ErrorAction SilentlyContinue |
    Where-Object { $_.Id -ne $SkipPid } |
    Stop-Process -Force

# Aguarda as portas liberarem.
Start-Sleep -Seconds 2

# Sobe tudo pela restart-app.bat numa nova janela cmd independente.
$bat = Join-Path $PSScriptRoot "restart-app.bat"
Start-Process -FilePath "cmd.exe" -ArgumentList "/k `"$bat`"" -WindowStyle Normal
