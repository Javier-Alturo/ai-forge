"""
Reminder Agent — Daemon que envia recordatorios por WhatsApp al usuario.

Corre en un hilo background (daemon=True). Cada 60 segundos revisa las
tareas del dia con reminder_time configurado y envia un mensaje de WhatsApp
cuando la hora coincide (+/- 1 minuto de tolerancia).

Uso:
    from agents.reminder_agent import start_reminder_daemon
    start_reminder_daemon()   # llamar 1 sola vez al inicio del sistema
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import date, datetime
from pathlib import Path

from agents.a2a_log import a2a_log

# ── Configuracion ─────────────────────────────────────────────────────────────
_ROOT          = Path(__file__).resolve().parent.parent
_TASKS_FILE    = _ROOT / "data" / "taskforge" / "tasks.json"
_REMINDED_FILE = _ROOT / "data" / "taskforge" / "reminded.json"

# Numero de WhatsApp destino, formato internacional sin '+' (ej. 573001234567)
WHATSAPP_NUMBER = os.environ.get("WSP_SYNC_NUMBER", "")

# Cuantos segundos entre cada revision
CHECK_INTERVAL_SECONDS = 60

# Tolerancia en minutos: si la hora del recordatorio cae dentro de este rango, se envia
TOLERANCE_MINUTES = 1


# ── WhatsApp sender ───────────────────────────────────────────────────────────

def _send_whatsapp(message: str) -> bool:
    """Envia un mensaje de WhatsApp usando Playwright (sesion persistente)."""
    try:
        from playwright.sync_api import sync_playwright
        import urllib.parse

        encoded = urllib.parse.quote(message)
        session_dir = str(_ROOT / "data" / "whatsapp_session")

        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=session_dir,
                headless=True,   # headless=True para que no interrumpa el trabajo
                channel="chrome",  # el Chromium propio de Playwright es bloqueado por WhatsApp Web
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.goto(
                f"https://web.whatsapp.com/send?phone={WHATSAPP_NUMBER}&text={encoded}",
                wait_until="domcontentloaded",
                timeout=30000,
            )

            send_btn = page.wait_for_selector(
                'button[aria-label="Enviar"]',
                timeout=25000,
            )
            time.sleep(1.0)
            send_btn.click()
            time.sleep(2.0)
            browser.close()

        a2a_log("reminder", "whatsapp", "sent", message[:80])
        return True

    except Exception as e:
        a2a_log("reminder", "whatsapp", "error", str(e)[:120])
        return False


# ── Logica de recordatorios ───────────────────────────────────────────────────

def _load_tasks() -> list:
    if not _TASKS_FILE.exists():
        return []
    try:
        return json.loads(_TASKS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _load_reminded() -> set:
    if not _REMINDED_FILE.exists():
        return set()
    try:
        data = json.loads(_REMINDED_FILE.read_text(encoding="utf-8"))
        return set(data)
    except Exception:
        return set()


def _save_reminded(reminded: set) -> None:
    _REMINDED_FILE.parent.mkdir(parents=True, exist_ok=True)
    _REMINDED_FILE.write_text(
        json.dumps(list(reminded), ensure_ascii=False),
        encoding="utf-8",
    )


def _check_and_send() -> None:
    """Revisa tareas con reminder_time y envia WhatsApp si toca."""
    now     = datetime.now()
    today   = date.today().isoformat()
    tasks   = _load_tasks()
    reminded = _load_reminded()

    for task in tasks:
        # Solo tareas de hoy, pendientes, con reminder_time, no enviadas aun
        if (
            task.get("date") != today
            or task.get("completed")
            or not task.get("reminder_time")
            or task["id"] in reminded
        ):
            continue

        try:
            reminder_dt = datetime.strptime(
                f"{today} {task['reminder_time']}", "%Y-%m-%d %H:%M"
            )
        except ValueError:
            continue

        diff_minutes = abs((now - reminder_dt).total_seconds() / 60)
        if diff_minutes <= TOLERANCE_MINUTES and now >= reminder_dt:
            prio_emoji = {"high": "URGENTE", "medium": "importante", "low": ""}.get(
                task.get("priority", "medium"), ""
            )
            msg_parts = [f"Recordatorio AI-Forge"]
            if prio_emoji:
                msg_parts.append(f"[{prio_emoji}]")
            msg_parts.append(f"\n\n{task['title']}")
            if task.get("description"):
                msg_parts.append(f"\n{task['description']}")
            msg_parts.append(f"\n\nHora: {task['reminder_time']}")

            message = " ".join(msg_parts[:2]) + "".join(msg_parts[2:])

            print(f"[ReminderAgent] Enviando recordatorio: {task['title']}")
            success = _send_whatsapp(message)

            if success:
                reminded.add(task["id"])
                _save_reminded(reminded)


# ── Daemon loop ───────────────────────────────────────────────────────────────

def _reminder_loop() -> None:
    """Loop principal del daemon. Corre indefinidamente cada 60 segundos."""
    print(f"[ReminderAgent] Daemon iniciado. Revisando cada {CHECK_INTERVAL_SECONDS}s -> {WHATSAPP_NUMBER}")
    a2a_log("reminder", "daemon", "started", WHATSAPP_NUMBER)

    while True:
        try:
            _check_and_send()
        except Exception as e:
            a2a_log("reminder", "daemon", "loop_error", str(e)[:120])
        time.sleep(CHECK_INTERVAL_SECONDS)


def start_reminder_daemon() -> threading.Thread:
    """Inicia el daemon de recordatorios en un hilo background.

    Llamar una sola vez al inicio del sistema (main.py o dashboard).
    El hilo es daemon=True: muere automaticamente cuando el proceso principal termina.
    """
    thread = threading.Thread(
        target=_reminder_loop,
        name="ReminderAgent",
        daemon=True,
    )
    thread.start()
    return thread


# ── Test rapido ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Enviando mensaje de prueba a", WHATSAPP_NUMBER)
    ok = _send_whatsapp(
        "Hola! Este es un mensaje de prueba del ReminderAgent de AI-Forge. "
        "Los recordatorios de tus tareas llegaran aqui."
    )
    print("Enviado:" if ok else "Error al enviar")
