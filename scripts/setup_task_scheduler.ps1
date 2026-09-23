# Cadastra a tarefa diaria do YouTube Content Creator no Windows Task Scheduler.
# Roda scripts/run_daily.py 1x/dia, que gera o video de cada canal ativo e
# notifica o dono (balao do Windows + log em data/logs/) ao final.
#
# Uso: abra o PowerShell nesta pasta e rode:
#   .\scripts\setup_task_scheduler.ps1
#
# Para desativar depois: Disable-ScheduledTask -TaskName "YouTube Content Creator - Geracao Diaria"
# Para remover: Unregister-ScheduledTask -TaskName "YouTube Content Creator - Geracao Diaria"

$ProjectDir = "C:\Desenvolvimento\artCover"
$PythonExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$ScriptPath = Join-Path $ProjectDir "scripts\run_daily.py"
$TaskName = "YouTube Content Creator - Geracao Diaria"

$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$ScriptPath`"" -WorkingDirectory $ProjectDir
$Trigger = New-ScheduledTaskTrigger -Daily -At 3:00AM
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Hours 1) -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$Principal = New-ScheduledTaskPrincipal -UserId $env:UserName -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force

Write-Host "Tarefa '$TaskName' cadastrada - roda todo dia as 3:00. Ollama precisa estar rodando na maquina nesse horario."
