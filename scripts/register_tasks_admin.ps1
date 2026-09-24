# ==============================================================================
# AI-Forge — Registro de Tareas Automaticas en Windows
# ==============================================================================

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  AI-Forge — Registrando tareas automaticas..." -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

$Root = Split-Path -Parent $PSScriptRoot
$PythonW = "pythonw.exe"

Write-Host ""
Write-Host "1. Registrando tarea: AI-Forge-Morning-Briefing..." -ForegroundColor Yellow
$trigger  = New-ScheduledTaskTrigger -AtLogOn
$action   = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$Root\scripts\startup_briefing.bat`""
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "AI-Forge-Morning-Briefing" -Trigger $trigger -Action $action -Settings $settings -Force | Out-Null
Write-Host "   OK — Tarea 'AI-Forge-Morning-Briefing' registrada exitosamente." -ForegroundColor Green

Write-Host ""
Write-Host "2. Registrando tarea: AI-Forge-Telegram-Listener..." -ForegroundColor Yellow
$trigger2  = New-ScheduledTaskTrigger -AtLogOn
$action2   = New-ScheduledTaskAction -Execute $PythonW -Argument "`"$Root\scripts\telegram_bot_listener.py`"" -WorkingDirectory $Root
$settings2 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 24)
Register-ScheduledTask -TaskName "AI-Forge-Telegram-Listener" -Trigger $trigger2 -Action $action2 -Settings $settings2 -Force | Out-Null
Write-Host "   OK — Tarea 'AI-Forge-Telegram-Listener' registrada exitosamente." -ForegroundColor Green

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Verificando tareas registradas..." -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Get-ScheduledTask | Where-Object { $_.TaskName -like "AI-Forge*" } | Format-Table TaskName, State -AutoSize
