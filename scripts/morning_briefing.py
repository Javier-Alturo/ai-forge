"""Morning Briefing Executor — Corre al inicio del PC, verifica servicios y despacha el briefing diario."""

from __future__ import annotations

import os
import sys
import time
import httpx
import re
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import date, datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# ══════════════════════════════════════════════════════════════════════════════
# SERVICIOS HEALTH & POLLING
# ══════════════════════════════════════════════════════════════════════════════

def wait_for_services(timeout_s: int = 60, interval_s: int = 5) -> bool:
    """Realiza polling para verificar si Ollama y ChromaDB están listos."""
    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    start_t = time.time()
    
    print(f"🔍 Iniciando verificación de servicios (timeout: {timeout_s}s)...")
    
    while time.time() - start_t < timeout_s:
        ollama_ready = False
        chroma_ready = False
        
        # Probar Ollama
        try:
            r = httpx.get(f"{ollama_base}/api/tags", timeout=2.0)
            if r.status_code == 200:
                ollama_ready = True
        except Exception:
            pass
            
        # Probar ChromaDB
        try:
            from agents.chroma_client import get_chroma_client
            client = get_chroma_client()
            client.list_collections()
            chroma_ready = True
        except Exception:
            pass
            
        if ollama_ready and chroma_ready:
            print("🟢 Ollama y ChromaDB están listos y respondiendo.")
            return True
            
        print(f"⏳ Esperando... (Ollama: {'LISTO' if ollama_ready else 'PENDIENTE'}, ChromaDB: {'LISTO' if chroma_ready else 'PENDIENTE'})")
        time.sleep(interval_s)
        
    print("⚠️ Timeout superado. Algunos servicios locales no están listos. Iniciando en modo degradado.")
    return False

# ══════════════════════════════════════════════════════════════════════════════
# GENERADOR EN MODO DEGRADADO (SIN LLM LOCAL)
# ══════════════════════════════════════════════════════════════════════════════

def generate_degraded_briefing() -> str:
    """Genera un briefing formateado a partir de llamadas directas a las tools si el LLM local no responde."""
    print("🤖 Generando briefing en modo degradado (llamadas a tools directas)...")
    
    from agents.morning_briefing_tools import (
        briefing_get_daily_note_tasks,
        briefing_get_past_pending_tasks,
        briefing_get_calendar_events,
        briefing_get_critical_emails,
        briefing_get_weather_briefing,
        briefing_get_rss_news,
        briefing_health_check
    )
    
    today = date.today().isoformat()
    
    # Ejecutamos las tools directamente con manejo de errores individual (Circuit Breaker)
    def safe_run(tool_fn, desc):
        try:
            return tool_fn.invoke({})
        except Exception as e:
            return f"⚠️ No se pudo obtener {desc}: {e}"
            
    tasks_today = safe_run(briefing_get_daily_note_tasks, "tareas de hoy")
    tasks_past = safe_run(briefing_get_past_pending_tasks, "tareas pasadas")
    calendar = safe_run(briefing_get_calendar_events, "calendario")
    emails = safe_run(briefing_get_critical_emails, "correos")
    weather = safe_run(briefing_get_weather_briefing, "clima")
    news = safe_run(briefing_get_rss_news, "noticias")
    health = safe_run(briefing_health_check, "estado del sistema")
    
    degraded_md = f"""# 🌅 Morning Briefing (Modo Degradado) — {today}

> ⚠️ **Nota:** El LLM local (Ollama) no se encuentra disponible. El briefing ha sido generado recopilando datos de APIs externas sin síntesis de IA.

### 🎯 Foco del Día
Revisar las tareas planificadas manualmente. Enfocarse en resolver las urgencias de calendario y atender correos electrónicos críticos al inicio de la jornada.

### 📝 Tareas del Día
{tasks_today}

### ⏳ Pendientes de días anteriores
{tasks_past}

### 📅 Agenda
{calendar}

### 🌦️ Clima y Consejos
{weather}

### 📧 Correos Críticos
{emails}

### 📰 Noticias del Sector (AI/Tech)
{news}

### 🛡️ Health Check del Sistema
{health}

⏱️ Generado: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
    return degraded_md

# ══════════════════════════════════════════════════════════════════════════════
# COMPACTACIÓN PARA TELEGRAM & ENVÍO
# ══════════════════════════════════════════════════════════════════════════════

def extract_section(text: str, section_title: str) -> str:
    """Extrae el contenido de una sección markdown."""
    pattern = rf"###\s*{re.escape(section_title)}[\r\n]+(.*?)(?=###|\Z)"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""

def send_telegram_briefing(briefing_text: str):
    """Extrae lo esencial del briefing y lo envía por Telegram en formato HTML limpio."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    
    if not token or not chat_id:
        print("⚠️ Telegram Bot Token o Chat ID no configurados. Se omite el envío.")
        return
        
    print("📤 Preparando envío del briefing compacto a Telegram...")
    
    # Extraer secciones clave
    foco = extract_section(briefing_text, "🎯 Foco del Día") or extract_section(briefing_text, "Foco del Día")
    tareas_raw = extract_section(briefing_text, "📝 Tareas del Día (Priorizadas)") or extract_section(briefing_text, "📝 Tareas del Día")
    agenda_raw = extract_section(briefing_text, "📅 Agenda")
    clima_raw = extract_section(briefing_text, "🌦️ Clima y Consejos")
    
    # Limpiar y resumir tareas (tomar las primeras 3)
    tareas_lines = [line.strip() for line in tareas_raw.splitlines() if line.strip().startswith("- [ ]")][:3]
    tareas_clean = "\n".join(tareas_lines) if tareas_lines else "No hay tareas pendientes asignadas."
    
    # Limpiar agenda (tomar las primeras 3 líneas)
    agenda_lines = [line.strip() for line in agenda_raw.splitlines() if line.strip()][:3]
    agenda_clean = "\n".join(agenda_lines) if agenda_lines else "Sin eventos hoy."

    # Limpiar clima
    clima_lines = [line.strip() for line in clima_raw.splitlines() if line.strip()][:2]
    clima_clean = "\n".join(clima_lines) if clima_lines else "Clima no disponible."

    # Construir HTML compatible
    html_msg = f"""🌅 <b>Morning Briefing — {date.today().isoformat()}</b>

🎯 <b>Foco del Día:</b>
<i>{foco or "Enfocarse en tareas críticas y revisar el dashboard local."}</i>

📝 <b>Top 3 Tareas:</b>
{tareas_clean}

📅 <b>Agenda:</b>
{agenda_clean}

🌦️ <b>Clima:</b>
{clima_clean}

🔗 <a href="http://localhost:8765">Ver Dashboard de Briefing Completo</a>
"""
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": html_msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true"
    }
    
    try:
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                print("✅ Briefing de Telegram enviado con éxito.")
            else:
                print(f"❌ Telegram respondió con status: {resp.status}")
    except Exception as e:
        print(f"❌ Error enviando mensaje a Telegram: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATION
# ══════════════════════════════════════════════════════════════════════════════

def run_briefing_flow() -> str:
    """Orquesta todo el flujo del briefing diario."""
    services_ready = wait_for_services(timeout_s=60, interval_s=5)
    
    briefing_text = ""
    
    if services_ready:
        print("🧠 Invocando al agente MorningBriefingAgent...")
        try:
            from agents.morning_briefing_agent import get_morning_briefing_agent
            agent = get_morning_briefing_agent()
            res = agent.invoke({"input": "Genera mi Morning Briefing completo para el día de hoy."})
            
            if res.status == "ok" and res.data:
                briefing_text = res.data
                print("✅ Briefing generado con éxito usando el Agente local.")
            else:
                print(f"⚠️ El agente falló o devolvió datos vacíos ({res.error}). Degradando...")
                briefing_text = generate_degraded_briefing()
        except Exception as e:
            print(f"⚠️ Error al importar o invocar al agente: {e}. Degradando...")
            briefing_text = generate_degraded_briefing()
    else:
        briefing_text = generate_degraded_briefing()
        
    # Guardar en Obsidian
    try:
        from agents.obsidian_tools import get_vault_path
        vault = get_vault_path()
        daily_notes_dir = vault / "Daily Notes"
        daily_notes_dir.mkdir(parents=True, exist_ok=True)
        
        today = date.today().isoformat()
        briefing_note_path = daily_notes_dir / f"{today}-briefing.md"
        briefing_note_path.write_text(briefing_text, encoding="utf-8")
        print(f"📔 Briefing guardado en Obsidian: {briefing_note_path}")
    except Exception as e:
        print(f"❌ No se pudo guardar la nota del briefing en Obsidian: {e}")
        
    # Enviar a Telegram
    send_telegram_briefing(briefing_text)
    
    return briefing_text

if __name__ == "__main__":
    # ─── Candado: evitar múltiples ejecuciones el mismo día ───
    lock_file = ROOT / "data" / "briefing_last_run.txt"
    today = date.today().isoformat()

    if "--force" not in sys.argv:
        if lock_file.exists():
            last_run = lock_file.read_text().strip()
            if last_run == today:
                print(f"✅ El Briefing ya se generó hoy ({today}). Usa --force para forzarlo.")
                sys.exit(0)

    # ─── Paso 0: Leer mensajes de Telegram y actualizar metas ───
    print("\n📬 [Paso 0] Verificando avances en metas a través de mensajes de Telegram...")
    goal_update_summary = ""
    try:
        from scripts.goal_tracker import check_and_update_goals
        goal_update_summary = check_and_update_goals()
    except Exception as e:
        print(f"⚠️ No se pudo actualizar metas: {e}")

    # ─── Paso 1: Generar el briefing ───
    briefing_text = run_briefing_flow()

    # ─── Paso 2: Si hubo avances, adjuntar al briefing enviado ───
    if goal_update_summary and briefing_text:
        try:
            TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
            CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
            if TOKEN and CHAT_ID:
                recap = f"🎯 *Actualización de Metas (ayer):*\n{goal_update_summary}"
                httpx.post(
                    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                    json={"chat_id": CHAT_ID, "text": recap},
                    timeout=10.0,
                )
        except Exception as e:
            print(f"⚠️ Error enviando recap de metas: {e}")

    # ─── Paso 3: Guardar candado ───
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text(today)
