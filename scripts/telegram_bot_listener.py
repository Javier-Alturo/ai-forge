"""Telegram Bot Listener — Escucha comandos como /daily y ejecuta rutinas de AI-Forge.

Seguridad: solo procesa mensajes de chats permitidos (core/telegram_auth.py) y nunca
imprime excepciones de httpx completas, porque la URL incluye el token del bot.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from agents.logger import get_logger
from core.telegram_auth import allowed_chat_ids, is_authorized

log = get_logger("telegram")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
_HTTP = httpx.Client(timeout=35.0)


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"


def get_updates(offset=None) -> list:
    params = {"timeout": 30, "allowed_updates": ["message"]}
    if offset:
        params["offset"] = offset
    try:
        r = _HTTP.get(_api("getUpdates"), params=params)
        if r.status_code == 200:
            return r.json().get("result", [])
    except (httpx.HTTPError, ValueError) as e:
        print(f"Error fetching updates: {type(e).__name__}")
    return []


def send_message(chat_id, text: str) -> None:
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        _HTTP.post(_api("sendMessage"), json=payload, timeout=10.0)
    except httpx.HTTPError as e:
        print(f"Error enviando mensaje: {type(e).__name__}")


def handle_briefing(chat_id) -> None:
    send_message(chat_id, "⏳ Generando Morning Briefing, dame unos segundos...")
    try:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "morning_briefing.py"), "--force"],
            cwd=str(ROOT),
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"❌ Briefing falló: {e}")
        send_message(chat_id, "❌ Ocurrió un error al generar el briefing.")


def handle_chat(chat_id, text: str) -> None:
    """Conversación libre con el orquestador local (un hilo de memoria por chat)."""
    print(f"💬 Mensaje recibido: {text[:50]}...")
    send_message(chat_id, "🤖 Procesando tu consulta (Qwen local)...")
    try:
        from agents.orchestrator import run_turn

        response_text = run_turn(text, thread_id=f"telegram_{chat_id}").content
    except Exception as e:  # frontera: el bot debe seguir vivo ante cualquier fallo del agente
        log.exception("Error procesando mensaje con IA: %s", type(e).__name__)
        send_message(chat_id, "⚠️ Error al procesar tu consulta con el modelo local.")
        return
    response_text = response_text or "⚠️ Completado, pero no hubo respuesta en texto."
    # Escapar para el modo HTML de Telegram
    send_message(chat_id, response_text.replace("<", "&lt;").replace(">", "&gt;"))


def handle_update(update: dict) -> None:
    msg = update.get("message", {})
    text = msg.get("text", "").strip()
    chat_id = msg.get("chat", {}).get("id")
    if not is_authorized(msg):
        print(f"⛔ Mensaje ignorado de chat no autorizado: {chat_id}")
        return
    if text in ("/daily", "/briefing"):
        print(f"📩 Comando {text} recibido. Generando briefing...")
        handle_briefing(chat_id)
    elif text and not text.startswith("/"):
        handle_chat(chat_id, text)


def main():
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN no configurado en .env.")
        sys.exit(1)
    if not allowed_chat_ids():
        print("❌ TELEGRAM_CHAT_ID no configurado en .env: el bot no respondería a nadie.")
        sys.exit(1)

    print("🤖 Telegram Listener de AI-Forge activo. Escuchando comandos...")
    offset = None
    while True:
        for update in get_updates(offset):
            offset = update["update_id"] + 1
            handle_update(update)
        time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nApagando listener...")
