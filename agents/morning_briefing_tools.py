"""Tools del agente de Morning Briefing (Obsidian, RAG, Calendario, Gmail, Clima, RSS, Health Check)."""

from __future__ import annotations

import os
import sys
import json
import httpx
import time
import urllib.request
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Any, List, Dict, Optional

from langchain_core.tools import tool
from dotenv import load_dotenv

# Ensure root is in sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.a2a_log import a2a_log
from agents.google_auth import get_google_credentials
from agents.obsidian_tools import get_vault_path
from agents.chroma_client import get_chroma_client

load_dotenv(ROOT / ".env")

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS & CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

def _get_api_key(name: str) -> Optional[str]:
    return os.getenv(name)

# ══════════════════════════════════════════════════════════════════════════════
# 1. HEALTH CHECK TOOL
# ══════════════════════════════════════════════════════════════════════════════

@tool
def briefing_health_check() -> str:
    """Verifica el estado de los servicios críticos de AI-Forge (Ollama, ChromaDB, FastMCP)."""
    a2a_log("morning_briefing", "system", "health_check", "Probing services...")
    report = []
    
    # 1. Ollama
    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    try:
        r = httpx.get(f"{ollama_base}/api/tags", timeout=3.0)
        if r.status_code == 200:
            models = [m.get("name") for m in r.json().get("models", [])]
            report.append(f"🟢 Ollama: En ejecución ({len(models)} modelos cargados: {', '.join(models[:3])})")
        else:
            report.append(f"🔴 Ollama: Respondió con código de error {r.status_code}")
    except Exception as e:
        report.append(f"🔴 Ollama: Fuera de servicio ({str(e)})")

    # 2. ChromaDB
    try:
        client = get_chroma_client()
        colls = client.list_collections()
        report.append(f"🟢 ChromaDB: En ejecución ({len(colls)} colecciones activas: {', '.join([c.name for c in colls])})")
    except Exception as e:
        report.append(f"🔴 ChromaDB: Fuera de servicio ({str(e)})")

    # 3. FastMCP / MCP connections
    try:
        from agents.mcp_client import _parse_mcp_connections
        conns = _parse_mcp_connections()
        if not conns:
            report.append("🟡 FastMCP: No hay servidores MCP externos configurados en mcp_servers.json")
        else:
            from agents.mcp_client import load_mcp_tools
            # load_mcp_tools es sync y ya maneja excepciones
            tools = load_mcp_tools()
            if tools:
                report.append(f"🟢 FastMCP: En ejecución (Conectado a {len(conns)} servidores, cargó {len(tools)} tools)")
            else:
                report.append("🔴 FastMCP: Servidores configurados pero no se pudieron cargar las herramientas (ver mcp_error.log)")
    except Exception as e:
        report.append(f"🔴 FastMCP: Error al comprobar conexiones MCP ({str(e)})")

    return "\n".join(report)

# ══════════════════════════════════════════════════════════════════════════════
# 2. TAREAS DEL DÍA (DAILY NOTE TOOL)
# ══════════════════════════════════════════════════════════════════════════════

@tool
def briefing_get_daily_note_tasks() -> str:
    """Lee la Daily Note de hoy en Obsidian, extrae las tareas pendientes ([ ]) e inicia con un template si no existe."""
    today = date.today().isoformat()
    a2a_log("morning_briefing", "obsidian", "get_daily_note_tasks", today)
    
    try:
        vault = get_vault_path()
    except Exception as e:
        return f"Error al acceder al Vault de Obsidian: {e}"
        
    daily_notes_dir = vault / "Daily Notes"
    daily_notes_dir.mkdir(parents=True, exist_ok=True)
    note_path = daily_notes_dir / f"{today}.md"
    
    created_new = False
    # Si la nota no existe, se crea con el template por defecto
    if not note_path.exists():
        template = f"""---
date: {today}
tags: [diario, tareas, briefing]
---

# Diario — {today}

## 🎯 Foco del Día
- (Generado por el briefing...)

## 📝 Tareas Pendientes
- [ ] Completar revisión de arquitectura de AI-Forge
- [ ] Revisar logs de agentes de ayer
- [ ] Hacer ejercicio

## 📓 Notas de la Jornada
"""
        try:
            note_path.write_text(template, encoding="utf-8")
            created_new = True
        except Exception as e:
            return f"Error al crear la Daily Note de hoy: {e}"
            
    try:
        content = note_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error al leer la Daily Note de hoy: {e}"
        
    # Extraer las tareas
    tasks = []
    for line in content.splitlines():
        if line.strip().startswith("- [ ]"):
            task_desc = line.replace("- [ ]", "").strip()
            if task_desc:
                tasks.append(task_desc)
                
    status = "Nueva Daily Note creada con template." if created_new else "Daily Note leída."
    if not tasks:
        return f"{status} No se encontraron tareas pendientes (- [ ]) registradas en la nota de hoy ({today})."
        
    lines = [f"- [ ] {t}" for t in tasks]
    result = f"{status} Tareas pendientes hoy ({today}):\n" + "\n".join(lines)
    
    # Integración con TaskForge (Metas y XP)
    try:
        tf_tasks_path = ROOT / "data" / "taskforge" / "tasks.json"
        if tf_tasks_path.exists():
            tf_data = json.loads(tf_tasks_path.read_text(encoding="utf-8"))
            active_goals = [t for t in tf_data if t.get("status") == "active"]
            if active_goals:
                result += "\n\n🎯 Metas Activas de TaskForge (AI-Forge):\n"
                for g in active_goals[:5]:
                    result += f"- {g.get('title', 'Meta')} (Prioridad: {g.get('priority', 'medium')}, XP: +{g.get('xp_reward', 0)})\n"
    except Exception as e:
        pass
        
    return result

# ══════════════════════════════════════════════════════════════════════════════
# 3. PENDIENTES DE AYER (SCANNER / RAG)
# ══════════════════════════════════════════════════════════════════════════════

@tool
def briefing_get_past_pending_tasks() -> str:
    """Busca en el vault (Daily Notes de los últimos 3 días) tareas que quedaron sin completar (- [ ])."""
    a2a_log("morning_briefing", "obsidian", "get_past_pending_tasks", "Scanning last 3 days...")
    
    try:
        vault = get_vault_path()
    except Exception as e:
        return f"Error al acceder al Vault de Obsidian: {e}"
        
    daily_notes_dir = vault / "Daily Notes"
    if not daily_notes_dir.exists():
        return "No existe el directorio de Daily Notes en el vault."
        
    today = date.today()
    pending_tasks: dict[str, list[str]] = {}
    
    # Escanear los últimos 3 días
    for i in range(1, 4):
        past_date = (today - timedelta(days=i)).isoformat()
        past_note = daily_notes_dir / f"{past_date}.md"
        if past_note.exists():
            try:
                content = past_note.read_text(encoding="utf-8")
                day_tasks = []
                for line in content.splitlines():
                    if line.strip().startswith("- [ ]"):
                        task_desc = line.replace("- [ ]", "").strip()
                        if task_desc:
                            day_tasks.append(task_desc)
                if day_tasks:
                    pending_tasks[past_date] = day_tasks
            except Exception as e:
                a2a_log("morning_briefing", "obsidian", "read_past_failed", f"{past_date}: {e}")
                
    if not pending_tasks:
        return "No se encontraron tareas pendientes en las notas diarias de los últimos 3 días."
        
    lines = []
    for day, tasks in pending_tasks.items():
        lines.append(f"📅 Hace { (today - date.fromisoformat(day)).days } día(s) ({day}):")
        for t in tasks:
            lines.append(f"  - [ ] {t}")
            
    return "Tareas arrastradas/pendientes de días anteriores:\n" + "\n".join(lines)

# ══════════════════════════════════════════════════════════════════════════════
# 4. CONTEXTO DE PROYECTOS (RAG OBSIDIAN)
# ══════════════════════════════════════════════════════════════════════════════

@tool
def briefing_get_projects_context() -> str:
    """Realiza una consulta RAG sobre el vault de Obsidian para extraer el contexto actual de proyectos y metas."""
    a2a_log("morning_briefing", "rag", "get_projects_context", "Querying project context...")
    
    # Reutilizar el consultor RAG integrado en rag_tools
    from agents.rag_tools import rag_query_obsidian
    
    queries = [
        "proyectos activos y metas de desarrollo en ai-forge",
        "tareas críticas pendientes de programar"
    ]
    
    results = []
    for q in queries:
        try:
            res = rag_query_obsidian.invoke(q)
            if res and not res.startswith("Error") and "No se encontraron" not in res:
                results.append(f"🔍 Contexto para '{q}':\n{res}\n")
        except Exception as e:
            results.append(f"⚠️ RAG Query falló para '{q}': {e}")
            
    if not results:
        # Fallback escaneo de notas de proyectos en la carpeta "01 - Arquitectura" o en el root
        try:
            vault = get_vault_path()
            project_files = list(vault.glob("*.md")) + list((vault / "01 - Arquitectura").glob("*.md"))
            fallback_text = []
            for pf in project_files[:3]:
                content = pf.read_text(encoding="utf-8")
                # Extraer las primeras líneas
                snippet = "\n".join(content.splitlines()[:15])
                fallback_text.append(f"📄 Nota: {pf.name}\n{snippet}...")
            if fallback_text:
                return "Fallback de notas de proyectos encontradas en el vault:\n\n" + "\n\n".join(fallback_text)
        except Exception:
            pass
        return "No se pudo recuperar contexto de proyectos activos (ejecuta primero rag_index_obsidian_vault)."
        
    return "\n".join(results)

# ══════════════════════════════════════════════════════════════════════════════
# 5. GOOGLE CALENDAR TOOL
# ══════════════════════════════════════════════════════════════════════════════

@tool
def briefing_get_calendar_events() -> str:
    """Conecta a Google Calendar API y lista los eventos agendados para el día de hoy."""
    a2a_log("morning_briefing", "google_calendar", "get_calendar_events", "Fetching today's events")
    
    creds = get_google_credentials()
    if creds is None:
        return "⚠️ Google Calendar: No disponible (Falta credentials.json o token de OAuth)."
        
    try:
        from googleapiclient.discovery import build
        svc = build("calendar", "v3", credentials=creds)
        
        # Obtener rango de hoy local
        now_local = datetime.now()
        start_of_day = datetime(now_local.year, now_local.month, now_local.day, 0, 0, 0)
        end_of_day = datetime(now_local.year, now_local.month, now_local.day, 23, 59, 59)
        
        # Convertir a ISO8601 con UTC Z
        # Google calendar API requiere formato RFC3339
        time_min = start_of_day.astimezone().isoformat()
        time_max = end_of_day.astimezone().isoformat()
        
        events_result = svc.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        
        items = events_result.get("items", [])
        if not items:
            return "No tienes eventos programados para hoy."
            
        lines = []
        for ev in items:
            start = ev["start"].get("dateTime", ev["start"].get("date"))
            # Formatear hora de inicio
            if "T" in start:
                dt = datetime.fromisoformat(start)
                start_str = dt.strftime("%H:%M")
            else:
                start_str = "Todo el día"
                
            lines.append(f"⏰ {start_str} - {ev.get('summary', '(Sin título)')}")
            
        return "Eventos de hoy en Google Calendar:\n" + "\n".join(lines)
        
    except Exception as e:
        return f"⚠️ Error consultando Google Calendar: {e}"

# ══════════════════════════════════════════════════════════════════════════════
# 6. GMAIL API TOOL
# ══════════════════════════════════════════════════════════════════════════════

@tool
def briefing_get_critical_emails() -> str:
    """Conecta a Gmail API y busca correos críticos recibidos hoy, ignorando alertas y boletines automáticos."""
    a2a_log("morning_briefing", "gmail", "get_critical_emails", "Fetching emails...")
    
    creds = get_google_credentials()
    if creds is None:
        return "⚠️ Gmail: No disponible (Falta credentials.json o token de OAuth)."
        
    try:
        from googleapiclient.discovery import build
        svc = build("gmail", "v1", credentials=creds)
        
        # Buscar correos no leídos o recibidos en las últimas 24 horas
        today_str = date.today().strftime("%Y/%m/%d")
        query = f"after:{today_str} is:unread"
        
        res = svc.users().messages().list(userId="me", q=query, maxResults=15).execute()
        msgs = res.get("messages", [])
        if not msgs:
            # Ampliar búsqueda a últimas 24h aunque estén leídos
            yesterday_str = (date.today() - timedelta(days=1)).strftime("%Y/%m/%d")
            query = f"after:{yesterday_str}"
            res = svc.users().messages().list(userId="me", q=query, maxResults=15).execute()
            msgs = res.get("messages", [])
            
        if not msgs:
            return "No hay correos recibidos recientemente."
            
        lines = []
        for m in msgs:
            mid = m["id"]
            meta = svc.users().messages().get(userId="me", id=mid, format="metadata").execute()
            headers = {h["name"].lower(): h["value"] for h in meta.get("payload", {}).get("headers", [])}
            subj = headers.get("subject", "(Sin asunto)")
            sender = headers.get("from", "Desconocido")
            snippet = meta.get("snippet", "")
            
            # Filtro inteligente básico de boletines/notificaciones automáticas
            ignore_keywords = [
                "newsletter", "boletin", "promo", "noreply", "no-reply", "digest", "notificacion",
                "notification", "oferta", "descuento", "update", "github", "linkedin", "security alert"
            ]
            is_automated = any(kw in subj.lower() or kw in sender.lower() or kw in snippet.lower() for kw in ignore_keywords)
            
            if not is_automated:
                lines.append(f"📧 De: {sender}\n   Asunto: {subj}\n   Extracto: {snippet[:150]}...\n")
                
        if not lines:
            return "No se detectaron correos críticos personales o de trabajo hoy. Todo el buzón restante parece ser alertas o newsletters."
            
        return "Correos críticos que requieren atención hoy:\n\n" + "\n".join(lines[:5])
        
    except Exception as e:
        return f"⚠️ Error consultando Gmail: {e}"

# ══════════════════════════════════════════════════════════════════════════════
# 7. CLIMA (OPENWEATHERMAP API)
# ══════════════════════════════════════════════════════════════════════════════

@tool
def briefing_get_weather_briefing() -> str:
    """Consulta el clima actual y pronóstico para Bogotá, Colombia y provee recomendaciones prácticas."""
    a2a_log("morning_briefing", "weather", "get_weather_briefing", "Fetching weather for Bogota...")
    
    api_key = _get_api_key("OPENWEATHER_API_KEY")
    if not api_key:
        # Fallback con clima típico de Bogotá, bien formateado e indicando que es simulación
        a2a_log("morning_briefing", "weather", "fallback_mock", "No API key found in .env")
        return """☁️ Clima en Bogotá (Simulado - Sin API Key):
  - Temperatura actual: 14°C
  - Condición: Nublado con probabilidad de lluvias por la tarde (55%).
  - Humedad: 82% | Viento: 10 km/h
  - Recomendación: El clima en Bogotá suele ser frío y cambiante hoy. Lleva paraguas y una chaqueta impermeable si vas a salir, ya que se prevén lluvias ligeras después del mediodía."""

    url = f"https://api.openweathermap.org/data/2.5/weather?q=Bogota,CO&appid={api_key}&units=metric&lang=es"
    try:
        r = httpx.get(url, timeout=5.0)
        if r.status_code != 200:
            raise ValueError(f"HTTP Status {r.status_code}")
            
        data = r.json()
        temp = data["main"]["temp"]
        feels_like = data["main"]["feels_like"]
        desc = data["weather"][0]["description"].capitalize()
        humidity = data["main"]["humidity"]
        
        # Generar recomendaciones dinámicas según la condición
        rec = "Lleva chaqueta cómoda. Clima típico bogotano."
        if "lluvia" in desc.lower() or "llovizna" in desc.lower():
            rec = "⚠️ Está lloviendo o se esperan lluvias. Paraguas e impermeable indispensables."
        elif temp < 12:
            rec = "🧥 Hace bastante frío. Abrígate bien con doble capa."
        elif temp > 18:
            rec = "☀️ Día inusualmente cálido. Ropa cómoda y bloqueador solar."
            
        return f"""🌤️ Clima en Bogotá (Real):
  - Temperatura: {temp:.1f}°C (Sensación: {feels_like:.1f}°C)
  - Condición: {desc}
  - Humedad: {humidity}%
  - Recomendación: {rec}"""
  
    except Exception as e:
        a2a_log("morning_briefing", "weather", "fetch_failed", str(e))
        return f"⚠️ Error al consultar el servicio de clima real: {e}. Fallback: Clima templado/lluvioso en Bogotá, lleva paraguas."

# ══════════════════════════════════════════════════════════════════════════════
# 8. NOTICIAS RSS FEED TOOL
# ══════════════════════════════════════════════════════════════════════════════

@tool
def briefing_get_rss_news() -> str:
    """Extrae las noticias más recientes y relevantes de RSS feeds sobre IA y tecnología (Hugging Face, Papers with Code, TechCrunch AI)."""
    a2a_log("morning_briefing", "rss", "get_rss_news", "Parsing feeds...")
    
    feeds = {
        "Hugging Face Blog": "https://huggingface.co/blog/feed.xml",
        "Papers with Code": "https://paperswithcode.com/media/rss/latest/",
        "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/"
    }
    
    report = []
    
    for name, url in feeds.items():
        try:
            # Hacer petición HTTP con timeout
            r = httpx.get(url, timeout=6.0, follow_redirects=True)
            if r.status_code != 200:
                report.append(f"📰 {name}: No se pudo leer (HTTP {r.status_code})")
                continue
                
            # Parsear XML nativo para evitar dependencias
            root = ET.fromstring(r.content)
            
            # El feed RSS estándar tiene la ruta root/channel/item
            items = []
            channel = root.find("channel")
            if channel is not None:
                items = channel.findall("item")
            else:
                # Atom feeds (Hugging Face puede usar Atom)
                # namespaces Atom
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                entries = root.findall("atom:entry", ns)
                if entries:
                    for entry in entries[:3]:
                        title_el = entry.find("atom:title", ns)
                        link_el = entry.find("atom:link", ns)
                        title = title_el.text if title_el is not None else "Sin título"
                        link = link_el.attrib.get("href", "") if link_el is not None else ""
                        items.append((title, link))
            
            if not items and channel is not None:
                # Si falló la extracción pero hay channel, intentar iterar directamente
                for item in channel.findall("item")[:3]:
                    t_el = item.find("title")
                    l_el = item.find("link")
                    title = t_el.text if t_el is not None else "Sin título"
                    link = l_el.text if l_el is not None else ""
                    items.append((title, link))
            elif not items:
                # Si no es Atom ni RSS estándar, intentar buscar todos los 'item'
                for item in root.findall(".//item")[:3]:
                    t_el = item.find("title")
                    l_el = item.find("link")
                    title = t_el.text if t_el is not None else "Sin título"
                    link = l_el.text if l_el is not None else ""
                    items.append((title, link))
                    
            if not items:
                report.append(f"📰 {name}: No se encontraron artículos en el feed.")
                continue
                
            # Formatear los primeros 3
            feed_lines = [f"📰 {name}:"]
            for title, link in items[:3]:
                # Si es una tupla
                if isinstance(title, tuple):
                    title, link = title
                title_clean = str(title).strip().replace("\n", " ")
                link_clean = str(link).strip()
                feed_lines.append(f"  • {title_clean} ({link_clean})")
            report.append("\n".join(feed_lines))
            
        except Exception as e:
            # Circuit breaker por feed individual: loguea pero no tira el script entero
            a2a_log("morning_briefing", "rss", "feed_failed", f"{name}: {e}")
            report.append(f"📰 {name}: Error de red o parsing ({str(e)})")
            
    return "\n\n".join(report)

# ══════════════════════════════════════════════════════════════════════════════
# REGISTER ALL TOOLS
# ══════════════════════════════════════════════════════════════════════════════

def get_briefing_tools() -> list[Any]:
    return [
        briefing_health_check,
        briefing_get_daily_note_tasks,
        briefing_get_past_pending_tasks,
        briefing_get_projects_context,
        briefing_get_calendar_events,
        briefing_get_critical_emails,
        briefing_get_weather_briefing,
        briefing_get_rss_news
    ]
