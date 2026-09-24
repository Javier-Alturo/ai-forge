"""
goal_tracker.py — Lee mensajes de Telegram enviados desde el último briefing,
los analiza con Qwen para detectar avances en metas, y actualiza tasks.json.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TASKS_PATH = ROOT / "data" / "taskforge" / "tasks.json"
GOALS_PATH = ROOT / "data" / "taskforge" / "goals.json"
LOG_PATH = ROOT / "data" / "goal_tracker_log.json"


def _load_tasks() -> list[dict]:
    """
    Carga las tareas del sistema. Si tasks.json esta vacio, lo puebla
    desde goals.json para que el tracker tenga datos con que trabajar.
    """
    tasks = []
    if TASKS_PATH.exists():
        raw = TASKS_PATH.read_text(encoding="utf-8").strip()
        if raw and raw != "[]":
            tasks = json.loads(raw)

    if not tasks and GOALS_PATH.exists():
        # Sincronizar metas de goals.json a tasks.json
        goals = json.loads(GOALS_PATH.read_text(encoding="utf-8"))
        tasks = []
        for g in goals:
            tasks.append({
                "id": g.get("id", ""),
                "title": g.get("title", "Meta"),
                "description": f"Meta de {g.get('stat', 'STR')} — progreso: {g.get('progress', 0)}%",
                "category": g.get("stat", "general").lower(),
                "priority": "high",
                "xp_reward": g.get("xp", 50),
                "status": "active",
                "progress": g.get("progress", 0),
                "created_at": g.get("created_at", ""),
                "progress_log": []
            })
        # Agregar tambien las metas custom de Upwork/Ingles/Marca Personal
        extra_tasks = [
            {
                "id": "upwork_01",
                "title": "Optimizar Perfil de Upwork y Enviar Propuestas",
                "category": "career",
                "priority": "high",
                "xp_reward": 300,
                "status": "active",
                "progress_log": []
            },
            {
                "id": "english_01",
                "title": "Estudio Intensivo de Ingles (10h/semana)",
                "category": "learning",
                "priority": "high",
                "xp_reward": 200,
                "status": "active",
                "progress_log": []
            },
            {
                "id": "brand_01",
                "title": "Marca Personal: AI Engineer",
                "category": "career",
                "priority": "medium",
                "xp_reward": 150,
                "status": "active",
                "progress_log": []
            }
        ]
        # Solo agregar si no estan ya
        existing_ids = {t["id"] for t in tasks}
        for et in extra_tasks:
            if et["id"] not in existing_ids:
                tasks.append(et)
        TASKS_PATH.parent.mkdir(parents=True, exist_ok=True)
        TASKS_PATH.write_text(json.dumps(tasks, indent=4, ensure_ascii=False), encoding="utf-8")
        print(f"INFO: tasks.json estaba vacio — sembradas {len(tasks)} metas desde goals.json")
    return tasks


# ══════════════════════════════════════════════════════════════════════════════
# 1. LEER MENSAJES RECIENTES DE TELEGRAM
# ══════════════════════════════════════════════════════════════════════════════

def get_messages_since_yesterday() -> list[str]:
    """
    Obtiene todos los mensajes enviados al bot desde las últimas 24h.
    Excluye comandos (que empiezan con /) y mensajes del propio bot.
    """
    if not TELEGRAM_TOKEN:
        return []

    # Calcular timestamp de hace 24h
    since_ts = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp())

    try:
        r = httpx.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
            params={"timeout": 10, "allowed_updates": ["message"], "offset": -100},
            timeout=15.0,
        )
        if r.status_code != 200:
            return []

        updates = r.json().get("result", [])
        messages = []

        for upd in updates:
            msg = upd.get("message", {})
            date_ts = msg.get("date", 0)
            text = msg.get("text", "").strip()

            # Solo mensajes recientes, sin comandos, con contenido
            if date_ts >= since_ts and text and not text.startswith("/"):
                messages.append(text)

        return messages
    except Exception as e:
        print(f"⚠️ Error leyendo mensajes de Telegram: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# 2. ANALIZAR MENSAJES CON QWEN
# ══════════════════════════════════════════════════════════════════════════════

def analyze_progress_with_ai(messages: list[str], tasks: list[dict]) -> dict:
    """
    Envía los mensajes + las metas actuales a Qwen y le pide que detecte
    si se reportó avance. Retorna un dict: {task_id: {"note": str, "completed": bool}}
    """
    if not messages:
        return {}

    active_tasks = [t for t in tasks if t.get("status") == "active"]
    if not active_tasks:
        return {}

    tasks_summary = "\n".join(
        f"- ID: {t['id']} | Título: {t.get('title','?')} | Categoría: {t.get('category','?')}"
        for t in active_tasks
    )

    user_messages = "\n".join(f"- {m}" for m in messages)

    prompt = f"""Eres un asistente personal de productividad.

El usuario envió estos mensajes por Telegram en las últimas 24 horas:
{user_messages}

Estas son sus metas activas actuales:
{tasks_summary}

Tu tarea: Analiza si alguno de los mensajes indica que el usuario trabajó, avanzó o completó alguna de esas metas. 
Por ejemplo: si dice "estudié inglés 2 horas" → eso es avance en la meta de Inglés.
Si dice "envié 3 propuestas en Upwork" → avance en la meta de Upwork.

Devuelve un JSON válido con esta estructura exacta (sin texto adicional, solo el JSON):
{{
  "updates": [
    {{
      "task_id": "ID_DE_LA_TAREA",
      "note": "Descripción del avance reportado",
      "completed": false
    }}
  ]
}}

Si no hay ningún avance reportado, devuelve: {{"updates": []}}
Solo incluye tareas donde haya avance claro. No inventes avances.
"""

    try:
        import httpx as _httpx
        ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        model = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")

        r = _httpx.post(
            f"{ollama_base}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=60.0,
        )
        if r.status_code != 200:
            return {}

        raw = r.json().get("response", "").strip()

        # Extraer JSON del texto de respuesta
        import re
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match:
            return {}

        result = json.loads(match.group())
        return {u["task_id"]: u for u in result.get("updates", [])}

    except Exception as e:
        print(f"⚠️ Error analizando mensajes con IA: {e}")
        return {}


# ══════════════════════════════════════════════════════════════════════════════
# 3. ACTUALIZAR tasks.json CON EL PROGRESO DETECTADO
# ══════════════════════════════════════════════════════════════════════════════

def update_tasks_with_progress(updates: dict) -> str:
    """
    Aplica los avances detectados al archivo tasks.json.
    Añade un campo 'progress_log' con las notas de cada avance.
    Retorna un resumen de los cambios.
    """
    if not updates or not TASKS_PATH.exists():
        return ""

    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    today = datetime.now().strftime("%Y-%m-%d")
    changes = []

    for task in tasks:
        task_id = task.get("id", "")
        if task_id in updates:
            upd = updates[task_id]
            note = upd.get("note", "")
            completed = upd.get("completed", False)

            # Añadir al log de progreso de la tarea
            if "progress_log" not in task:
                task["progress_log"] = []

            task["progress_log"].append({
                "date": today,
                "note": note
            })

            # Si se completó, marcarla
            if completed:
                task["status"] = "completed"
                task["completed_at"] = today

            changes.append(f"✅ '{task.get('title','?')}': {note}")

    if changes:
        TASKS_PATH.write_text(json.dumps(tasks, indent=4, ensure_ascii=False), encoding="utf-8")

        # Guardar log de seguimiento
        log = []
        if LOG_PATH.exists():
            log = json.loads(LOG_PATH.read_text(encoding="utf-8"))
        log.append({"date": today, "changes": changes})
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.write_text(json.dumps(log, indent=4, ensure_ascii=False), encoding="utf-8")

    return "\n".join(changes)


# ══════════════════════════════════════════════════════════════════════════════
# 4. FUNCIÓN PRINCIPAL — llamar desde morning_briefing.py
# ══════════════════════════════════════════════════════════════════════════════

def check_and_update_goals() -> str:
    """
    Flujo completo:
    1. Lee mensajes de Telegram de las últimas 24h
    2. Analiza con Qwen si hay avances en las metas
    3. Actualiza tasks.json
    4. Retorna resumen (para incluir en el briefing)
    """
    print("📬 Leyendo mensajes de Telegram de las últimas 24h...")
    messages = get_messages_since_yesterday()

    if not messages:
        print("📭 No hay mensajes nuevos para analizar.")
        return ""

    print(f"📩 {len(messages)} mensaje(s) recibido(s). Analizando avances con IA...")

    if not TASKS_PATH.exists():
        return ""

    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    updates = analyze_progress_with_ai(messages, tasks)

    if not updates:
        print("🔍 Sin avances en metas detectados.")
        return ""

    summary = update_tasks_with_progress(updates)
    print(f"🎯 Metas actualizadas:\n{summary}")
    return summary


if __name__ == "__main__":
    result = check_and_update_goals()
    if result:
        print(f"\nResumen de cambios:\n{result}")
    else:
        print("Sin cambios en las metas.")
