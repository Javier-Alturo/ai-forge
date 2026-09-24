"""Setup Morning Briefing — Script de configuración de carpetas, dependencias, variables .env y registro en Task Scheduler."""

from __future__ import annotations

import os
import sys
import subprocess
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def check_env_vars():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    print("📝 Verificando variables de entorno en .env...")
    env_path = ROOT / ".env"
    if not env_path.exists():
        print("⚠️ .env no encontrado. Copiando desde .env.example...")
        import shutil
        shutil.copy(ROOT / ".env.example", env_path)

    content = env_path.read_text(encoding="utf-8")
    updates = []

    required_vars = {
        "TELEGRAM_BOT_TOKEN": "# Token del bot de Telegram para notificaciones del Briefing",
        "TELEGRAM_CHAT_ID": "# Chat ID de Telegram para recibir el Briefing",
        "OPENWEATHER_API_KEY": "# API Key de OpenWeatherMap para clima real de Bogotá",
    }

    for var, comment in required_vars.items():
        if f"{var}=" not in content:
            updates.append(f"\n{comment}\n{var}=\n")

    if updates:
        print(f"➕ Añadiendo variables de Briefing faltantes a {env_path.name}...")
        with open(env_path, "a", encoding="utf-8") as f:
            f.writelines(updates)
    else:
        print("✅ Todas las variables requeridas están declaradas en .env.")

def create_folders():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    print("📂 Verificando estructura de carpetas...")
    vault_path_str = os.getenv("OBSIDIAN_VAULT_PATH", "")
    if vault_path_str:
        daily_notes = Path(vault_path_str) / "Daily Notes"
        daily_notes.mkdir(parents=True, exist_ok=True)
        print(f"✅ Directorio Daily Notes verificado: {daily_notes}")
    else:
        print("⚠️ OBSIDIAN_VAULT_PATH no está definido en .env. Por favor edítalo primero.")

def register_task_scheduler():
    print("⏰ Registrando tarea de Windows Task Scheduler...")
    bat_path = ROOT / "scripts" / "startup_briefing.bat"
    
    # Comando de PowerShell para crear la tarea al Logon
    ps_command = (
        f'Register-ScheduledTask -TaskName "AI-Forge-Morning-Briefing" '
        f'-Trigger (New-ScheduledTaskTrigger -AtLogOn) '
        f'-Action (New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c {bat_path}") '
        f'-Settings (New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries) '
        f'-Force'
    )
    
    print("\nPowerShell Command:")
    print(ps_command)
    print("\nIntentando registrar la tarea de forma automática (requiere permisos de Administrador)...")
    
    try:
        res = subprocess.run(
            ["powershell", "-Command", ps_command],
            capture_output=True,
            text=True,
            check=False
        )
        if res.returncode == 0:
            print("🎉 Tarea 'AI-Forge-Morning-Briefing' registrada exitosamente en Task Scheduler de Windows!")
        else:
            print("⚠️ No se pudo registrar la tarea automáticamente (probablemente por falta de privilegios de Administrador).")
            print("👉 Para registrarla de forma manual, abre PowerShell como Administrador y ejecuta el siguiente comando:")
            print("-" * 80)
            print(ps_command)
            print("-" * 80)
    except Exception as e:
        print(f"❌ Error al ejecutar PowerShell: {e}")

def main():
    print("=" * 80)
    print("⚙️  CONFIGURACIÓN DEL MORNING BRIEFING INTELIGENTE")
    print("=" * 80)
    
    check_env_vars()
    create_folders()
    register_task_scheduler()
    
    print("\n✅ Configuración finalizada.")
    print("Recuerda rellenar TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID y OPENWEATHER_API_KEY en tu .env si deseas datos reales.")
    print("Puedes arrancar el panel web local manualmente con: 'py scripts/morning_briefing_dashboard.py'")

if __name__ == "__main__":
    main()
