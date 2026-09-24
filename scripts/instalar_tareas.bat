@echo off
:: =========================================================
:: Instalar Tareas de AI-Forge con Permisos de Administrador
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
echo   Instalando Tareas de Windows (AI-Forge)
echo =================================================

:: Cambiar al directorio del script
cd /d "%~dp0"

:: Ejecutar el script de powershell
powershell -ExecutionPolicy Bypass -File "%~dp0register_tasks_admin.ps1"

echo.
echo Operacion completada. Puedes cerrar esta ventana.
pause
