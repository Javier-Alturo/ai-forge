"""
setup_wsp_cron.py — Configura el Task Scheduler de Windows para ejecutar
wsp_daily_sync.py automáticamente cada noche.

Uso:
  py scripts/setup_wsp_cron.py --install    # Instala la tarea programada
  py scripts/setup_wsp_cron.py --uninstall  # Elimina la tarea
  py scripts/setup_wsp_cron.py --status     # Muestra el estado actual
  py scripts/setup_wsp_cron.py --test       # Ejecuta ahora mismo para probar
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT     = Path(__file__).resolve().parent.parent
SCRIPT   = ROOT / "agents" / "wsp_daily_sync.py"
TASK_NAME = "AI-Forge-WSP-DailySync"

# Hora de ejecución (22:00 por defecto = 10PM)
HOUR   = "22"
MINUTE = "00"


def get_python() -> str:
    """Retorna el path al intérprete Python correcto."""
    # Intentar 'py' primero (Windows), luego sys.executable
    try:
        result = subprocess.run(["py", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            return "py"
    except FileNotFoundError:
        pass
    return sys.executable


def install_task(hour: str = HOUR, minute: str = MINUTE, send_summary: bool = False):
    """Registra la tarea en Windows Task Scheduler."""
    python = get_python()
    args = f"--send-summary" if send_summary else ""

    # Comando completo
    action = f'"{python}" "{SCRIPT}" {args}'.strip()

    cmd = [
        "schtasks", "/Create",
        "/TN", TASK_NAME,
        "/TR", action,
        "/SC", "DAILY",
        "/ST", f"{hour}:{minute}",
        "/F",        # Sobreescribir si ya existe
        "/RL", "HIGHEST",  # Correr con privilegios elevados
        "/RU", "SYSTEM",   # Como SYSTEM para no requerir login
    ]

    print(f"⚙️  Instalando tarea: '{TASK_NAME}'")
    print(f"   Hora: {hour}:{minute} diariamente")
    print(f"   Comando: {action}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✅ Tarea instalada correctamente")
        print(f"\n💡 Para que envíe el resumen por WhatsApp, ejecuta con --send-summary")
    else:
        print(f"❌ Error al instalar: {result.stderr}")
        print(f"\n📌 Alternativa manual:")
        print(f"   Abre 'Programador de tareas' de Windows y crea una tarea con:")
        print(f"   Programa: {python}")
        print(f"   Argumentos: \"{SCRIPT}\" {args}")
        print(f"   Desencadenador: Diariamente a las {hour}:{minute}")


def uninstall_task():
    """Elimina la tarea del Task Scheduler."""
    cmd = ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✅ Tarea '{TASK_NAME}' eliminada")
    else:
        print(f"❌ Error: {result.stderr}")


def show_status():
    """Muestra el estado actual de la tarea."""
    cmd = ["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST"]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="cp850")
    if result.returncode == 0:
        print(result.stdout)
    else:
        print(f"⚠️  La tarea '{TASK_NAME}' no está instalada")
        print(f"   Ejecuta: py scripts/setup_wsp_cron.py --install")


def run_test(messages: str = None, dry_run: bool = True):
    """Ejecuta el script ahora mismo para pruebas."""
    python = get_python()
    args = [python, str(SCRIPT)]

    if dry_run:
        args.append("--dry-run")
    if messages:
        args += ["--messages", messages]

    print(f"🧪 Ejecutando prueba {'(DRY-RUN)' if dry_run else '(REAL)'}...")
    print(f"   {'Sin' if not messages else 'Con'} mensajes manuales\n")

    result = subprocess.run(args, capture_output=False)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Configurar WSP Daily Sync como tarea de Windows")
    parser.add_argument("--install",      action="store_true", help="Instalar la tarea programada")
    parser.add_argument("--uninstall",    action="store_true", help="Desinstalar la tarea")
    parser.add_argument("--status",       action="store_true", help="Ver estado de la tarea")
    parser.add_argument("--test",         action="store_true", help="Ejecutar ahora (dry-run)")
    parser.add_argument("--test-real",    action="store_true", help="Ejecutar ahora (REAL, modifica datos)")
    parser.add_argument("--test-msg",     type=str, default=None,
                        help="Probar con mensajes manuales (ej: 'hice ejercicio y grabé video')")
    parser.add_argument("--hour",         type=str, default=HOUR, help=f"Hora de ejecución (default: {HOUR})")
    parser.add_argument("--minute",       type=str, default=MINUTE, help=f"Minuto (default: {MINUTE})")
    parser.add_argument("--send-summary", action="store_true", help="Enviar resumen por WhatsApp")
    args = parser.parse_args()

    if args.install:
        install_task(args.hour, args.minute, args.send_summary)
    elif args.uninstall:
        uninstall_task()
    elif args.status:
        show_status()
    elif args.test or args.test_msg:
        run_test(messages=args.test_msg, dry_run=True)
    elif args.test_real:
        run_test(messages=args.test_msg, dry_run=False)
    else:
        parser.print_help()
        print(f"\n📌 Ejemplo rápido para probar:")
        print(f'   py scripts/setup_wsp_cron.py --test --test-msg "hoy hice ejercicio y grabé un video en inglés"')


if __name__ == "__main__":
    main()
