# -*- coding: utf-8 -*-
"""
wsp_daily_sync.py — Agente de sincronización diaria via WhatsApp.

Flujo:
  1. Lee los mensajes de WhatsApp Business del número configurado (usando whatsapp_api local).
  2. Usa Ollama/LLM para interpretar cuáles hábitos/tareas se completaron.
  3. Marca los hábitos en TaskForge (actualiza metas y XP).
  4. Guarda un resumen detallado en Obsidian.
  5. Envía un resumen de vuelta al número de WhatsApp con lo hecho, pendiente y métricas.

Uso:
  py agents/wsp_daily_sync.py                  # Sincronización manual
  py agents/wsp_daily_sync.py --dry-run         # Solo muestra, no modifica nada
  py agents/wsp_daily_sync.py --send-summary    # También envía resumen por WSP

Cron (Windows Task Scheduler): cada noche a las 22:00
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

# Forzar UTF-8 en la consola de Windows (para emojis)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

# Aseguramos que el root del proyecto esté en sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# ── Importar herramientas existentes ─────────────────────────────────────────
from agents.taskforge_tools import (
    _load, _save, _today, _now,
    _HABITS_FILE, _GOALS_FILE, _TASKS_FILE, _LOGS_FILE,
)

# ── Configuración ─────────────────────────────────────────────────────────────
WSP_NUMBER = os.getenv("WSP_SYNC_NUMBER", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
OBSIDIAN_VAULT  = os.getenv("OBSIDIAN_VAULT_PATH", "")

_SESSION_DIR = str(ROOT / "data" / "whatsapp_session")
_HORA_RE = re.compile(r"(\d{1,2}):(\d{2})\s*([ap])\.?\s*m\.?", re.IGNORECASE)


# ══════════════════════════════════════════════════════════════════════════════
# 1. LEER MENSAJES DE WHATSAPP
# ══════════════════════════════════════════════════════════════════════════════

def _parse_row_text(text: str) -> tuple[str, Optional[str]]:
    """Separa un mensaje renderizado ('cuerpo\\ncuerpo\\nHH:MM a./p. m.') en (body, hora)."""
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if not lines:
        return "", None
    if _HORA_RE.search(lines[-1]) and len(lines) > 1:
        return "\n".join(lines[:-1]).strip(), lines[-1].strip()
    if _HORA_RE.search(lines[-1]):
        return "", lines[-1].strip()
    return "\n".join(lines).strip(), None


def _hora_to_timestamp(hora_str: str, base_date: date) -> float:
    """Convierte 'HH:MM a. m./p. m.' (formato WhatsApp Web en español) a epoch de hoy."""
    m = _HORA_RE.search(hora_str)
    if not m:
        return datetime.combine(base_date, datetime.min.time()).timestamp()
    hour, minute, ampm = int(m.group(1)), int(m.group(2)), m.group(3).lower()
    if ampm == "p" and hour != 12:
        hour += 12
    if ampm == "a" and hour == 12:
        hour = 0
    return datetime.combine(base_date, datetime.min.time().replace(hour=hour, minute=minute)).timestamp()


def fetch_wsp_messages_today(max_messages: int = 20) -> list[dict]:
    """Lee los mensajes recientes del chat WSP (self-chat) usando Playwright,
    reutilizando la sesión persistida en data/whatsapp_session.

    Requiere:
    - Sesión ya vinculada una vez con scripts/wsp_login_bootstrap.py.
    - channel="chrome" (el Chromium que trae Playwright por defecto es
      bloqueado por el detector de navegador de WhatsApp Web con el mensaje
      "WhatsApp works with Google Chrome 100+").

    Limitación conocida: WhatsApp Web no expone la fecha completa de cada
    mensaje en el DOM salvo por separadores visuales ("Hoy"/"Ayer") que solo
    se renderizan si se hace scroll hasta ellos. En vez de intentar detectar
    esos separadores (frágil y depende de la estructura interna de WhatsApp),
    esta función toma los últimos `max_messages` mensajes visibles en el chat
    (los más recientes, ya que la conversación abre con scroll al final) y
    asume que corresponden al día de hoy. Para el caso de uso real —sync diario
    o el hook de un demo en vivo— esto es correcto porque el chat se usa a
    diario. Si el chat no ha tenido actividad hoy, esos mensajes serán de un
    día anterior y el LLM los interpretará igual como "hoy" — no hay chequeo
    de fecha real. Aceptable para este proyecto personal; no usar tal cual en
    un producto multi-usuario sin resolver el chequeo de fecha real.
    """
    from playwright.sync_api import sync_playwright

    raw_texts: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=_SESSION_DIR,
                headless=True,
                channel="chrome",
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            try:
                page = browser.pages[0] if browser.pages else browser.new_page()
                page.goto(
                    f"https://web.whatsapp.com/send?phone={WSP_NUMBER}",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                page.wait_for_selector("div#main", timeout=30000)
                page.wait_for_timeout(3000)

                main = page.query_selector("div#main")
                rows = main.query_selector_all('div[data-testid^="conv-msg-"]') if main else []
                # Extraer el texto MIENTRAS el navegador sigue abierto — los
                # ElementHandle dejan de ser validos apenas se cierra el browser.
                raw_texts = [r.inner_text() for r in rows[-max_messages:]]
            finally:
                browser.close()
    except Exception as e:
        print(f"⚠️  No se pudo leer WhatsApp via Playwright: {e}")
        print("   ¿Corriste scripts/wsp_login_bootstrap.py para vincular la sesión?")
        return []

    today = date.today()
    messages: list[dict] = []
    for text in raw_texts:
        body, hora = _parse_row_text(text)
        if not body or not hora:
            continue
        ts = _hora_to_timestamp(hora, today)
        messages.append({"body": body, "from_me": True, "timestamp": ts})

    return messages


# ══════════════════════════════════════════════════════════════════════════════
# 2. INTERPRETAR MENSAJES CON LLM
# ══════════════════════════════════════════════════════════════════════════════

def build_prompt(messages: list[dict], habits: list[dict]) -> str:
    """Construye el prompt para que el LLM interprete qué hábitos se completaron."""

    habits_list = "\n".join(
        f"  - ID: {h['id']} | Título: {h['title']}"
        for h in habits
    )

    msgs_text = "\n".join(
        f"  [{datetime.fromtimestamp(m['timestamp']).strftime('%H:%M') if isinstance(m['timestamp'], (int,float)) else '??:??'}] "
        f"{'YO:' if m['from_me'] else 'OTRO:'} {m['body']}"
        for m in messages
    ) or "  (sin mensajes hoy)"

    return f"""Eres un asistente que analiza mensajes de WhatsApp y determina qué hábitos diarios completó el usuario.

HÁBITOS DISPONIBLES (con sus IDs):
{habits_list}

MENSAJES DE HOY ({_today()}):
{msgs_text}

TAREA:
Analiza los mensajes y determina cuáles hábitos fueron completados hoy.
Busca menciones directas o indirectas (ej: "hice ejercicio" → "Entreno o actividad física 30 min", 
"leí un rato" → "Leer 20 páginas", "medité" → "Meditar 10 min", etc.)

Responde ÚNICAMENTE con un JSON válido en este formato exacto:
{{
  "completed_habit_ids": ["id1", "id2"],
  "uncompleted_habit_ids": ["id3"],
  "raw_metrics": {{
    "notas_adicionales": "cualquier métrica extra mencionada (peso, tiempo, distancia, etc.)"
  }},
  "confidence": "high|medium|low",
  "interpretation_notes": "breve explicación de cómo interpretaste los mensajes"
}}

Si no hay mensajes o no se puede determinar, retorna listas vacías pero no inventes datos.
Solo JSON, sin markdown, sin texto adicional."""


def call_llm(prompt: str) -> Optional[str]:
    """Llama al LLM local (Ollama) y retorna la respuesta."""
    import urllib.request, json as _json

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1},
    }

    try:
        body = _json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = _json.loads(resp.read().decode())
            return result.get("response", "")
    except Exception as e:
        print(f"⚠️  Error llamando al LLM: {e}")
        return None


def parse_llm_response(response: str) -> dict:
    """Extrae el JSON de la respuesta del LLM."""
    # Intentar extraer JSON aunque haya texto alrededor
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    return {
        "completed_habit_ids": [],
        "uncompleted_habit_ids": [],
        "raw_metrics": {},
        "confidence": "low",
        "interpretation_notes": "No se pudo parsear la respuesta del LLM",
    }


# ══════════════════════════════════════════════════════════════════════════════
# 3. APLICAR CAMBIOS A TASKFORGE
# ══════════════════════════════════════════════════════════════════════════════

def mark_habit_complete(habit: dict, habits: list, goals: list, logs: list, dry_run: bool = False) -> str:
    """Marca un hábito como completado y actualiza metas."""
    habit_id = habit["id"]

    if habit.get("last_completed") == _today():
        return f"  ⏭️  '{habit['title']}' ya estaba completado hoy"

    if not dry_run:
        # Actualizar racha
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        if habit.get("last_completed") == yesterday:
            habit["streak"] = habit.get("streak", 0) + 1
        else:
            habit["streak"] = 1
        habit["last_completed"] = _today()

        # Actualizar meta
        goal = next((g for g in goals if g["id"] == habit["goal_id"]), None)
        xp_earned = habit.get("xp_reward", 20)
        if goal:
            goal["progress"] = min(100.0, round(goal["progress"] + habit.get("increment", 0.5), 2))
            goal["xp"] = goal.get("xp", 0) + xp_earned
            XP_PER_LEVEL = 200
            goal["level"] = goal["xp"] // XP_PER_LEVEL

            # Propagar a metas semanales relacionadas
            stat_key = goal.get("stat")
            if stat_key:
                for other_g in goals:
                    if other_g["id"] != goal["id"] and other_g.get("stat") == stat_key:
                        inc = habit.get("increment", 0.5)
                        if other_g["id"] == "w_gym_01" and habit_id == "gym_h001":
                            inc = 20.0
                        elif other_g["id"] == "w_eng_01" and habit_id == "e89a2afe":
                            inc = 33.33
                        other_g["progress"] = min(100.0, round(other_g["progress"] + inc, 2))
                        other_g["xp"] = other_g.get("xp", 0) + xp_earned
                        other_g["level"] = other_g["xp"] // XP_PER_LEVEL

        logs.append({
            "habit_id": habit_id,
            "action": "habit_completed",
            "xp_earned": xp_earned,
            "source": "wsp_sync",
            "date": _today(),
            "created_at": _now(),
        })

    streak_icon = "🔥🔥" if habit.get("streak", 0) >= 7 else "🔥" if habit.get("streak", 0) >= 3 else "✅"
    prefix = "[DRY-RUN] " if dry_run else ""
    return f"  {streak_icon} {prefix}'{habit['title']}' | Racha: {habit.get('streak', 1)} días"


def apply_changes(analysis: dict, dry_run: bool = False) -> tuple[list[str], list[str]]:
    """Aplica los cambios determinados por el LLM a los datos de TaskForge."""
    habits = _load(_HABITS_FILE)
    goals  = _load(_GOALS_FILE)
    logs   = _load(_LOGS_FILE)

    completed_lines = []
    skipped_lines   = []

    # Hábitos completados
    for habit_id in analysis.get("completed_habit_ids", []):
        habit = next((h for h in habits if h["id"] == habit_id), None)
        if habit:
            result = mark_habit_complete(habit, habits, goals, logs, dry_run)
            completed_lines.append(result)
        else:
            skipped_lines.append(f"  ⚠️  ID '{habit_id}' no encontrado")

    # Guardar cambios
    if not dry_run and completed_lines:
        _save(_HABITS_FILE, habits)
        _save(_GOALS_FILE, goals)
        _save(_LOGS_FILE, logs)

    # Hábitos NO completados (mencionados explícitamente)
    all_habits = _load(_HABITS_FILE)
    completed_ids = set(h["id"] for h in all_habits if h.get("last_completed") == _today())
    for habit in all_habits:
        if habit["id"] not in completed_ids:
            skipped_lines.append(f"  ⬜ '{habit['title']}' — pendiente")

    return completed_lines, skipped_lines


# ══════════════════════════════════════════════════════════════════════════════
# 4. GENERAR RESUMEN
# ══════════════════════════════════════════════════════════════════════════════

def generate_summary(completed: list[str], pending: list[str], analysis: dict) -> str:
    """Genera un resumen legible del día."""
    goals  = _load(_GOALS_FILE)
    habits = _load(_HABITS_FILE)

    today = _today()
    total_habits = len(habits)
    done_habits  = sum(1 for h in habits if h.get("last_completed") == today)
    completion_pct = (done_habits / total_habits * 100) if total_habits > 0 else 0

    # Resumen de metas
    goals_summary = []
    for g in goals:
        if not g["id"].startswith("w_"):  # Solo metas largas
            goals_summary.append(f"  📌 {g['title']}: {g['progress']:.1f}% | Nivel {g.get('level', 0)} | {g.get('xp', 0)} XP")

    weekly_summary = []
    for g in goals:
        if g["id"].startswith("w_"):  # Solo metas semanales
            weekly_summary.append(f"  📅 {g['title']}: {g['progress']:.1f}%")

    # Rachas top
    top_streaks = sorted(habits, key=lambda h: h.get("streak", 0), reverse=True)[:3]
    streak_lines = [f"  🔥 {h['title']}: {h.get('streak', 0)} días" for h in top_streaks if h.get("streak", 0) > 0]

    summary = f"""╔══════════════════════════════════════╗
║     📊 RESUMEN DIARIO — {today}     ║
╚══════════════════════════════════════╝

✅ COMPLETADO HOY ({done_habits}/{total_habits} hábitos — {completion_pct:.0f}%):
{chr(10).join(completed) if completed else '  (ninguno detectado)'}

⬜ PENDIENTE:
{chr(10).join(pending) if pending else '  ¡Todo completado! 🎉'}

🎯 PROGRESO DE METAS:
{chr(10).join(goals_summary) if goals_summary else '  (sin metas)'}

📅 METAS SEMANALES:
{chr(10).join(weekly_summary) if weekly_summary else '  (sin metas semanales)'}
"""

    if streak_lines:
        summary += f"\n🔥 RACHAS ACTIVAS:\n{chr(10).join(streak_lines)}\n"

    if analysis.get("raw_metrics", {}).get("notas_adicionales"):
        summary += f"\n📝 MÉTRICAS EXTRA:\n  {analysis['raw_metrics']['notas_adicionales']}\n"

    notes = analysis.get("interpretation_notes", "")
    if notes:
        summary += f"\n🤖 Interpretación IA: {notes}\n"

    summary += f"\n⏱️  Sincronizado: {_now()}"
    return summary


# ══════════════════════════════════════════════════════════════════════════════
# 5. GUARDAR EN OBSIDIAN
# ══════════════════════════════════════════════════════════════════════════════

def save_to_obsidian(summary: str, completed: list[str], pending: list[str], analysis: dict) -> str:
    """Guarda el resumen del día en Obsidian."""
    if not OBSIDIAN_VAULT:
        return "⚠️  OBSIDIAN_VAULT_PATH no configurado — resumen no guardado"

    vault = Path(OBSIDIAN_VAULT)
    if not vault.exists():
        return f"⚠️  Vault no encontrado en: {OBSIDIAN_VAULT}"

    today = _today()
    # Carpeta: Diario/<año>/<mes>/
    folder = vault / "Diario" / today[:4] / today[5:7]
    folder.mkdir(parents=True, exist_ok=True)

    note_path = folder / f"{today} — Resumen Diario.md"

    habits = _load(_HABITS_FILE)
    goals  = _load(_GOALS_FILE)

    # Formato enriquecido para Obsidian con frontmatter YAML
    content = f"""---
date: {today}
tags: [diario, taskforge, habitos, resumen]
completados: {sum(1 for h in habits if h.get('last_completed') == today)}
total_habitos: {len(habits)}
---

# 📊 Resumen Diario — {today}

## ✅ Hábitos Completados
{"".join(f'- [x] {line.strip().lstrip("✅🔥⏭️ ")}\\n' for line in completed) if completed else "- [ ] (ninguno detectado)\\n"}

## ⬜ Hábitos Pendientes
{"".join(f'- [ ] {line.strip().lstrip("⬜ ")}\\n' for line in pending) if pending else "- [x] ¡Todo completado! 🎉\\n"}

## 🎯 Progreso de Metas
"""
    for g in goals:
        content += f"- **{g['title']}**: {g['progress']:.1f}% | Nivel {g.get('level', 0)} | {g.get('xp', 0)} XP\n"

    content += "\n## 🤖 Análisis IA\n"
    content += f"- **Confianza**: {analysis.get('confidence', 'N/A')}\n"
    content += f"- **Notas**: {analysis.get('interpretation_notes', 'N/A')}\n"

    if analysis.get("raw_metrics", {}).get("notas_adicionales"):
        content += f"\n## 📝 Métricas Extra\n{analysis['raw_metrics']['notas_adicionales']}\n"

    content += f"\n---\n*Generado automáticamente por wsp_daily_sync — {_now()}*\n"

    note_path.write_text(content, encoding="utf-8")
    return f"✅ Resumen guardado en Obsidian: {note_path}"


# ══════════════════════════════════════════════════════════════════════════════
# 6. ENVIAR RESUMEN POR WHATSAPP
# ══════════════════════════════════════════════════════════════════════════════

def send_wsp_message(text: str) -> bool:
    """Envía un mensaje de texto por WhatsApp al número configurado."""
    import urllib.request, json as _json

    # Formato esperado por whatsapp-web.js API (evolution-api / wppconnect / etc.)
    payload = {
        "number": f"{WSP_NUMBER}@c.us",
        "text": text,
    }

    endpoints_to_try = [
        f"{WSP_API_URL}/api/sendText",
        f"{WSP_API_URL}/api/send-message",
        f"{WSP_API_URL}/message/sendText/{WSP_NUMBER}",
    ]

    for url in endpoints_to_try:
        try:
            body = _json.dumps(payload).encode()
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status < 300:
                    print(f"  ✅ Mensaje enviado via {url}")
                    return True
        except Exception:
            continue

    print(f"  ⚠️  No se pudo enviar el mensaje (servidor WSP no disponible)")
    return False


def build_wsp_summary(summary: str) -> str:
    """Convierte el resumen detallado a un formato amigable para WhatsApp."""
    # WhatsApp no tiene markdown, usar emojis y texto plano
    return summary.replace("╔", "").replace("╚", "").replace("╗", "").replace("╝", "").replace("║", "").replace("═", "").strip()


def build_wsp_reply(completed: list[str], pending: list[str]) -> str:
    """Respuesta corta y limpia para el chat de WhatsApp (sin arte ASCII de
    terminal). Pensada para el listener en vivo — algo que se vea bien en
    una pantalla de celular, no el reporte completo de generate_summary()."""
    goals  = _load(_GOALS_FILE)
    habits = _load(_HABITS_FILE)
    today = _today()
    total = len(habits)
    done  = sum(1 for h in habits if h.get("last_completed") == today)

    def _title(line: str) -> str:
        m = re.search(r"'([^']+)'", line)
        return m.group(1) if m else line.strip()

    lines = [f"✅ ¡Listo! Actualicé tu progreso de hoy ({done}/{total} hábitos):"]
    if completed:
        for c in completed:
            lines.append(f"  ✔ {_title(c)}")
    else:
        lines.append("  (no detecté ningún hábito nuevo en tu mensaje)")

    pend_titles = [_title(p) for p in pending if "pendiente" in p]
    if pend_titles:
        lines.append("\n📌 Próximo en tu lista:")
        for t in pend_titles[:3]:
            lines.append(f"  ⬜ {t}")

    goals_lines = [
        f"  🎯 {g['title']}: {g['progress']:.1f}%"
        for g in goals if not g["id"].startswith("w_")
    ]
    if goals_lines:
        lines.append("\n📊 Tus metas:")
        lines.extend(goals_lines)

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="WSP Daily Sync — Sincronización de hábitos via WhatsApp")
    parser.add_argument("--dry-run",      action="store_true", help="Simula sin modificar datos")
    parser.add_argument("--send-summary", action="store_true", help="Envía el resumen por WhatsApp")
    parser.add_argument("--no-llm",       action="store_true", help="Omite el LLM (solo muestra mensajes)")
    parser.add_argument("--messages",     type=str, default=None,
                        help="Texto manual de mensajes (para pruebas sin WSP conectado)")
    args = parser.parse_args()

    print(f"\n{'='*55}")
    print(f"  🤖 WSP Daily Sync — {_today()}")
    print(f"{'='*55}\n")

    # ── Paso 1: Leer mensajes ────────────────────────────────
    if args.messages:
        # Modo prueba: mensajes pasados como argumento
        messages = [{
            "body": args.messages,
            "from_me": True,
            "timestamp": datetime.now().timestamp(),
        }]
        print(f"📨 Usando mensajes manuales: '{args.messages}'")
    else:
        print(f"📨 Leyendo mensajes de WhatsApp ({WSP_NUMBER})...")
        messages = fetch_wsp_messages_today()
        print(f"   → {len(messages)} mensajes encontrados hoy")

    for m in messages:
        t = datetime.fromtimestamp(m["timestamp"]).strftime("%H:%M") if isinstance(m["timestamp"], (int, float)) else "??"
        who = "YO" if m["from_me"] else "OTRO"
        print(f"   [{t}] {who}: {m['body'][:80]}")

    # ── Paso 2: Interpretar con LLM ─────────────────────────
    habits = _load(_HABITS_FILE)
    analysis = {
        "completed_habit_ids": [],
        "uncompleted_habit_ids": [],
        "raw_metrics": {},
        "confidence": "low",
        "interpretation_notes": "LLM omitido",
    }

    if not args.no_llm and messages:
        print(f"\n🧠 Interpretando mensajes con {OLLAMA_MODEL}...")
        prompt   = build_prompt(messages, habits)
        response = call_llm(prompt)

        if response:
            analysis = parse_llm_response(response)
            print(f"   → Confianza: {analysis.get('confidence', '?')}")
            print(f"   → Hábitos completados: {analysis.get('completed_habit_ids', [])}")
            print(f"   → Notas: {analysis.get('interpretation_notes', '')[:100]}")
        else:
            print("   ⚠️  LLM no respondió — sin cambios automáticos")
    elif not messages:
        print("\n⚠️  Sin mensajes de hoy — no hay nada que interpretar")

    # ── Paso 3: Aplicar cambios ──────────────────────────────
    print(f"\n{'🔄 DRY-RUN — ' if args.dry_run else ''}📝 Aplicando cambios...")
    completed, pending = apply_changes(analysis, dry_run=args.dry_run)

    # ── Paso 4: Generar resumen ──────────────────────────────
    summary = generate_summary(completed, pending, analysis)
    print(f"\n{summary}")

    # ── Paso 5: Guardar en Obsidian ──────────────────────────
    print("\n📔 Guardando en Obsidian...")
    obsidian_result = save_to_obsidian(summary, completed, pending, analysis)
    print(f"   {obsidian_result}")

    # ── Paso 6: Enviar por WhatsApp ──────────────────────────
    if args.send_summary:
        print(f"\n📱 Enviando resumen por WhatsApp a {WSP_NUMBER}...")
        wsp_text = build_wsp_summary(summary)
        send_wsp_message(wsp_text)

    print(f"\n{'='*55}")
    print(f"  ✅ Sincronización completada — {_now()}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
