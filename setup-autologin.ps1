# Configura autologin da conta Admin e execução do start.bat na inicialização.
# Rodar UMA VEZ como Administrador.

$username = "Admin"
$password = "Italia2018"
$startBat = "C:\src\pics\start.bat"

# --- 1. Autologin ---
$regPath = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
Set-ItemProperty -Path $regPath -Name "AutoAdminLogon"  -Value "1"
Set-ItemProperty -Path $regPath -Name "DefaultUserName"  -Value $username
Set-ItemProperty -Path $regPath -Name "DefaultPassword"  -Value $password
Set-ItemProperty -Path $regPath -Name "DefaultDomainName" -Value $env:COMPUTERNAME
Write-Host "Autologin configurado para '$username'."

# --- 2. start.bat na inicialização (Task Scheduler, roda na sessão do usuário) ---
$taskName = "PICS_Startup"

# Remove task anterior se existir
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action  = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$startBat`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $username
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 0)
$principal = New-ScheduledTaskPrincipal -UserId $username -LogonType Interactive -RunLevel Highest

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Description "Inicia backend+Caddy do PICS no logon" | Out-Null

Write-Host "Task '$taskName' registrada: executa '$startBat' no logon de '$username'."
Write-Host ""
Write-Host "Pronto. Reinicie o PC para testar."
