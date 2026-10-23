"""Tools del agente de Morning Briefing (Obsidian, RAG, Health Check).

Las tools que llaman servicios externos (Calendar, Gmail, Clima, RSS) viven en
agents/briefing_external_tools.py y se re-exportan aquí por compatibilidad.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from langchain_core.tools import tool

# Ensure root is in sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.a2a_log import a2a_log
from agents.briefing_external_tools import (
    briefing_get_calendar_events,
    briefing_get_critical_emails,
    briefing_get_rss_news,
    briefing_get_weather_briefing,
)
from agents.chroma_client import get_chroma_client
from agents.logger import get_logger
from agents.obsidian_tools import get_vault_path

load_dotenv(ROOT / ".env")
log = get_logger("morning_briefing")

__all__ = [
    "briefing_get_calendar_events",
    "briefing_get_critical_emails",
    "briefing_get_daily_note_tasks",
    "briefing_get_past_pending_tasks",
    "briefing_get_projects_context",
    "briefing_get_rss_news",
    "briefing_get_weather_briefing",
    "briefing_health_check",
    "get_briefing_tools",
]

_DAILY_TEMPLATE = """---
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


def extract_open_tasks(markdown: str) -> list[str]:
    """Devuelve el texto de cada tarea abierta (`- [ ] ...`) de una nota Markdown."""
    tasks = []
    for line in markdown.splitlines():
        if line.strip().startswith("- [ ]"):
            desc = line.replace("- [ ]", "").strip()
            if desc:
                tasks.append(desc)
    return tasks


# ── 1. Health check ───────────────────────────────────────────────────────────

def _check_ollama() -> str:
    base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    try:
        r = httpx.get(f"{base}/api/tags", timeout=3.0)
        if r.status_code != 200:
            return f"🔴 Ollama: Respondió con código de error {r.status_code}"
        models = [m.get("name") for m in r.json().get("models", [])]
    except (httpx.HTTPError, ValueError) as e:
        return f"🔴 Ollama: Fuera de servicio ({e})"
    return f"🟢 Ollama: En ejecución ({len(models)} modelos cargados: {', '.join(models[:3])})"


def _check_chroma() -> str:
    try:
        colls = get_chroma_client().list_collections()
    except Exception as e:
        log.exception("ChromaDB health check failed")
        return f"🔴 ChromaDB: Fuera de servicio ({e})"
    return f"🟢 ChromaDB: En ejecución ({len(colls)} colecciones activas: {', '.join(c.name for c in colls)})"


def _check_mcp() -> str:
    try:
        from agents.mcp_client import _parse_mcp_connections, load_mcp_tools

        conns = _parse_mcp_connections()
        if not conns:
            return "🟡 FastMCP: No hay servidores MCP externos configurados en mcp_servers.json"
        tools = load_mcp_tools()
    except Exception as e:
        log.exception("MCP health check failed")
        return f"🔴 FastMCP: Error al comprobar conexiones MCP ({e})"
    if tools:
        return f"🟢 FastMCP: En ejecución (Conectado a {len(conns)} servidores, cargó {len(tools)} tools)"
    return "🔴 FastMCP: Servidores configurados pero no se pudieron cargar las herramientas (ver mcp_error.log)"


@tool
def briefing_health_check() -> str:
    """Verifica el estado de los servicios críticos de AI-Forge (Ollama, ChromaDB, FastMCP)."""
    a2a_log("morning_briefing", "system", "health_check", "Probing services...")
    return "\n".join([_check_ollama(), _check_chroma(), _check_mcp()])


# ── 2. Tareas del día (Daily Note) ────────────────────────────────────────────

def _taskforge_goals_text() -> str:
    tf_tasks_path = ROOT / "data" / "taskforge" / "tasks.json"
    try:
        tf_data = json.loads(tf_tasks_path.read_text(encoding="utf-8")) if tf_tasks_path.exists() else []
    except (OSError, ValueError):
        log.warning("No se pudo leer TaskForge tasks.json", exc_info=True)
        return ""
    active = [t for t in tf_data if t.get("status") == "active"][:5]
    if not active:
        return ""
    lines = [
        f"- {g.get('title', 'Meta')} (Prioridad: {g.get('priority', 'medium')}, XP: +{g.get('xp_reward', 0)})"
        for g in active
    ]
    return "\n\n🎯 Metas Activas de TaskForge (AI-Forge):\n" + "\n".join(lines) + "\n"


@tool
def briefing_get_daily_note_tasks() -> str:
    """Lee la Daily Note de hoy en Obsidian, extrae las tareas pendientes ([ ]) e inicia con un template si no existe."""
    today = date.today().isoformat()
    a2a_log("morning_briefing", "obsidian", "get_daily_note_tasks", today)
    try:
        daily_notes_dir = get_vault_path() / "Daily Notes"
        daily_notes_dir.mkdir(parents=True, exist_ok=True)
        note_path = daily_notes_dir / f"{today}.md"
        created_new = not note_path.exists()
        if created_new:
            note_path.write_text(_DAILY_TEMPLATE.format(today=today), encoding="utf-8")
        content = note_path.read_text(encoding="utf-8")
    except (ValueError, OSError) as e:
        return f"Error al acceder a la Daily Note de hoy: {e}"

    status = "Nueva Daily Note creada con template." if created_new else "Daily Note leída."
    tasks = extract_open_tasks(content)
    if not tasks:
        return f"{status} No se encontraron tareas pendientes (- [ ]) registradas en la nota de hoy ({today})."
    result = f"{status} Tareas pendientes hoy ({today}):\n" + "\n".join(f"- [ ] {t}" for t in tasks)
    return result + _taskforge_goals_text()


# ── 3. Pendientes de días anteriores ──────────────────────────────────────────

@tool
def briefing_get_past_pending_tasks() -> str:
    """Busca en el vault (Daily Notes de los últimos 3 días) tareas que quedaron sin completar (- [ ])."""
    a2a_log("morning_briefing", "obsidian", "get_past_pending_tasks", "Scanning last 3 days...")
    try:
        daily_notes_dir = get_vault_path() / "Daily Notes"
    except ValueError as e:
        return f"Error al acceder al Vault de Obsidian: {e}"
    if not daily_notes_dir.exists():
        return "No existe el directorio de Daily Notes en el vault."

    lines = []
    for days_ago in range(1, 4):
        past_date = (date.today() - timedelta(days=days_ago)).isoformat()
        past_note = daily_notes_dir / f"{past_date}.md"
        try:
            tasks = extract_open_tasks(past_note.read_text(encoding="utf-8")) if past_note.exists() else []
        except OSError as e:
            a2a_log("morning_briefing", "obsidian", "read_past_failed", f"{past_date}: {e}")
            continue
        if tasks:
            lines.append(f"📅 Hace {days_ago} día(s) ({past_date}):")
            lines += [f"  - [ ] {t}" for t in tasks]

    if not lines:
        return "No se encontraron tareas pendientes en las notas diarias de los últimos 3 días."
    return "Tareas arrastradas/pendientes de días anteriores:\n" + "\n".join(lines)


# ── 4. Contexto de proyectos (RAG Obsidian) ───────────────────────────────────

def _projects_fallback() -> str | None:
    """Primeras líneas de hasta 3 notas del vault si el RAG no devuelve nada."""
    try:
        vault = get_vault_path()
        project_files = list(vault.glob("*.md")) + list((vault / "01 - Arquitectura").glob("*.md"))
        snippets = [
            f"📄 Nota: {pf.name}\n" + "\n".join(pf.read_text(encoding="utf-8").splitlines()[:15]) + "..."
            for pf in project_files[:3]
        ]
    except (ValueError, OSError):
        log.warning("Fallback de notas de proyectos falló", exc_info=True)
        return None
    if not snippets:
        return None
    return "Fallback de notas de proyectos encontradas en el vault:\n\n" + "\n\n".join(snippets)


@tool
def briefing_get_projects_context() -> str:
    """Realiza una consulta RAG sobre el vault de Obsidian para extraer el contexto actual de proyectos y metas."""
    a2a_log("morning_briefing", "rag", "get_projects_context", "Querying project context...")
    from agents.rag_tools import rag_query_obsidian

    queries = ["proyectos activos y metas de desarrollo en ai-forge", "tareas críticas pendientes de programar"]
    results = []
    for q in queries:
        try:
            res = rag_query_obsidian.invoke(q)
        except Exception as e:
            log.exception("RAG query failed: %s", q)
            results.append(f"⚠️ RAG Query falló para '{q}': {e}")
            continue
        if res and not res.startswith("Error") and "No se encontraron" not in res:
            results.append(f"🔍 Contexto para '{q}':\n{res}\n")

    if results:
        return "\n".join(results)
    return _projects_fallback() or (
        "No se pudo recuperar contexto de proyectos activos (ejecuta primero rag_index_obsidian_vault)."
    )


def get_briefing_tools() -> list[Any]:
    return [
        briefing_health_check,
        briefing_get_daily_note_tasks,
        briefing_get_past_pending_tasks,
        briefing_get_projects_context,
        briefing_get_calendar_events,
        briefing_get_critical_emails,
        briefing_get_weather_briefing,
        briefing_get_rss_news,
    ]
