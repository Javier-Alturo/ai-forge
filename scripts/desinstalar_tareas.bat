@echo off
:: =========================================================
:: Desinstalar Tareas de AI-Forge con Permisos de Administrador
:: =========================================================

:: Verificar si tenemos permisos de administrador
net session >nul 2>&1
if %errorLevel% == 0 (
    goto :admin
) else (
    echo Solicitando permisos de administrador...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

:admin
echo =================================================
echo   Desinstalando Tareas de Windows (AI-Forge)
echo =================================================

:: Eliminar tareas programadas
schtasks /delete /tn "AI-Forge-Morning-Briefing" /f
schtasks /delete /tn "AI-Forge-Telegram-Listener" /f

:: Terminar cualquier proceso de pythonw que pueda estar corriendo
taskkill /f /im pythonw.exe

echo.
echo Operacion completada. Las tareas han sido eliminadas y el bot apagado.
pause
