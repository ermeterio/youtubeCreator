# Cadastra a tarefa de inicializacao do YouTube Content Creator no Windows
# Task Scheduler - sobe o servidor (pipeline.settings_ui) automaticamente
# quando a maquina liga e o dono faz logon, sem precisar abrir terminal.
#
# Uso: abra o PowerShell nesta pasta e rode:
#   .\scripts\setup_startup_task.ps1
#
# Para desativar depois: Disable-ScheduledTask -TaskName "YouTube Content Creator - Subir Servidor"
# Para remover: Unregister-ScheduledTask -TaskName "YouTube Content Creator - Subir Servidor"

$ProjectDir = "C:\Desenvolvimento\artCover"
$PythonExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$TaskName = "YouTube Content Creator - Subir Servidor"
$LogPath = Join-Path $ProjectDir "data\logs\server_stdout.log"

# "cmd /c" redireciona stdout/stderr pro mesmo log usado nos restarts manuais
# (ver histórico de deploy do projeto) - Register-ScheduledTaskAction não tem
# jeito nativo de redirecionar saída de um .exe direto.
$Command = "/c `"`"$PythonExe`" -m pipeline.settings_ui >> `"$LogPath`" 2>&1`""

$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $Command -WorkingDirectory $ProjectDir
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:UserName
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
$Principal = New-ScheduledTaskPrincipal -UserId $env:UserName -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force

Write-Host "Tarefa '$TaskName' cadastrada - sobe o servidor automaticamente no próximo logon/reinício."
Write-Host "Pra subir agora sem reiniciar a máquina: Start-ScheduledTask -TaskName `"$TaskName`""
