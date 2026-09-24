"""Telegram Bot Listener — Escucha comandos como /daily y ejecuta rutinas de AI-Forge."""

import os
import sys
import json
import time
import httpx
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 30, "allowed_updates": ["message"]}
    if offset:
        params["offset"] = offset
        
    try:
        r = httpx.get(url, params=params, timeout=35.0)
        if r.status_code == 200:
            return r.json().get("result", [])
    except Exception as e:
        print(f"Error fetching updates: {e}")
    return []

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        httpx.post(url, json=payload, timeout=10.0)
    except Exception as e:
        print(f"Error enviando mensaje: {e}")

def main():
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN no configurado en .env.")
        sys.exit(1)
        
    print("🤖 Telegram Listener de AI-Forge activo. Escuchando comandos...")
    offset = None
    
    while True:
        updates = get_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1
            
            msg = update.get("message", {})
            text = msg.get("text", "").strip()
            chat_id = msg.get("chat", {}).get("id")
            
            if text == "/daily" or text == "/briefing":
                print(f"📩 Comando {text} recibido del chat {chat_id}. Generando briefing...")
                send_message(chat_id, "⏳ Generando Morning Briefing, dame unos segundos...")
                
                # Importar y ejecutar el script forzando ejecución
                import subprocess
                try:
                    subprocess.run(
                        ["python", str(ROOT / "scripts" / "morning_briefing.py"), "--force"],
                        cwd=str(ROOT),
                        check=True
                    )
                except Exception as e:
                    send_message(chat_id, f"❌ Ocurrió un error al generar el briefing: {e}")
            elif text and not text.startswith("/"):
                # Conversación libre con Qwen a través del Orquestador
                print(f"💬 Mensaje recibido: {text[:50]}...")
                send_message(chat_id, "🤖 Procesando tu consulta (Qwen local)...")
                
                try:
                    from agents.orchestrator import get_orchestrator_graph
                    orchestrator = get_orchestrator_graph()
                    
                    # Invocar al LangGraph local
                    res = orchestrator.invoke(
                        {"messages": [("user", text)]},
                        {"configurable": {"thread_id": f"telegram_{chat_id}"}}
                    )
                    
                    response_text = ""
                    # Buscar la respuesta en el estado final (lista de mensajes)
                    if "messages" in res and res["messages"]:
                        response_text = res["messages"][-1].content
                    elif "agent" in res and "messages" in res["agent"]:
                        response_text = res["agent"]["messages"][-1].content
                        
                    if not response_text:
                        response_text = "⚠️ Completado, pero no hubo respuesta en texto."
                        
                    # Limpiar texto para HTML de Telegram
                    response_text = response_text.replace("<", "&lt;").replace(">", "&gt;")
                    send_message(chat_id, response_text)
                    
                except Exception as e:
                    print(f"❌ Error procesando mensaje con IA: {e}")
                    send_message(chat_id, f"⚠️ Error al conectar con Qwen local: {e}")
                    
        time.sleep(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nApagando listener...")
