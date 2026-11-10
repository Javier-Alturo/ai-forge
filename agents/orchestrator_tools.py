"""Tools the orchestrator can call: one per sub-agent, plus direct RAG/lead tools and
SkillForge-generated dynamic tools.

Sub-agent tools are generated from SUBAGENTS (a data table) instead of one
hand-written function each; tool names and descriptions are unchanged.
"""

from __future__ import annotations

import importlib
import inspect
import os
from typing import Any, Callable

from langchain_core.runnables.config import ensure_config
from langchain_core.tools import BaseTool, StructuredTool, tool

from agents.a2a_log import a2a_log
from agents.logger import get_logger
from agents.subagent_runner import invoke_subagent

log = get_logger("orchestrator")

# (registry name, "module:getter", tool description)
# The orchestrator prompt does not list the tools, so each description must say WHEN to use the
# tool in the user's words, not how it is built.
SUBAGENTS: list[tuple[str, str, str]] = [
    ("web_search", "agents.web_search_agent:get_web_search_agent",
     "Busca en internet. Úsalo cuando el usuario pida información actual o externa: noticias, precios, "
     "resultados, versiones nuevas, 'busca en la web', 'averigua', 'verifica'."),
    ("memory", "agents.memory_agent:get_memory_agent",
     "Memoria a largo plazo del usuario. Úsalo para GUARDAR algo ('recuerda que', 'acuérdate de', "
     "'ten presente', 'guarda que') y para RECUPERAR lo guardado ('¿qué recuerdas de...?', "
     "'¿qué sabes de mis...?', '¿qué te conté sobre...?'). No es para la conversación actual."),
    ("code", "agents.code_agent_graph:get_code_agent",
     "Escribe y EJECUTA código Python. Úsalo cuando el usuario pida un script, un programa, una función, "
     "'calcula con Python', 'ejecuta', 'corre'. Para redes neuronales o PyTorch usa el agente de redes."),
    ("neural_network", "agents.neural_network_agent:get_neural_network_agent",
     "Redes neuronales con PyTorch. Úsalo SIEMPRE que el usuario pida diseñar o entrenar una red, un "
     "perceptrón, una CNN, una LSTM, un autoencoder o cualquier modelo de deep learning."),
    ("fitness", "agents.fitness_agent:get_fitness_agent",
     "Entrenamiento físico del usuario. Úsalo para registrar sesiones ('hoy hice...', 'anota que corrí...') "
     "y para consultar rutina de gimnasio, récords, marcas, progreso, lesiones o el reporte semanal."),
    ("taskforge", "agents.taskforge_agent:get_taskforge_agent",
     "Productividad personal. Úsalo para tareas (agregar, completar, listar pendientes), metas a largo "
     "plazo, hábitos y rachas, recordatorios ('recuérdame a las...') y métricas de la semana."),
    ("marketing", "agents.marketing_agent:get_marketing_agent",
     "Marketing y ventas. Úsalo cuando el usuario pida REDACTAR mensajes de outreach, mensajes en frío, "
     "propuestas para clientes, posts o copy comercial, investigar un nicho, o buscar clientes y leads."),
    ("file", "agents.file_agent:get_file_agent",
     "Archivos y carpetas del computador. Úsalo para leer, escribir, listar, mover, copiar o buscar "
     "archivos locales."),
    ("email", "agents.email_agent:get_email_agent",
     "Correo Gmail del usuario en solo lectura. Úsalo para listar o buscar correos, ver la bandeja de "
     "entrada o saber quién escribió. No puede enviar correos."),
    ("calendar", "agents.calendar_agent:get_calendar_agent",
     "Google Calendar del usuario. Úsalo para ver la agenda, consultar eventos o reuniones de un día, y "
     "para crear, agendar o borrar eventos y citas."),
    ("voice", "agents.voice_agent:get_voice_agent",
     "Micrófono. Úsalo cuando el usuario pida grabar su voz, dictar, escuchar o transcribir audio a texto."),
    ("image", "agents.image_agent:get_image_agent",
     "Genera imágenes. Úsalo cuando el usuario pida crear, generar, dibujar o hacer una imagen, "
     "ilustración, retrato o dibujo."),
    ("computer_use", "agents.computer_use_agent:get_computer_use_agent",
     "Pantalla del computador. Úsalo cuando el usuario pida una captura o pantallazo, saber qué hay en "
     "la pantalla o qué ventana está abierta, o controlar mouse, teclado y aplicaciones."),
    ("github", "agents.github_agent:get_github_agent",
     "GitHub remoto por API. Úsalo para consultar repositorios en GitHub: listar, abrir o cerrar issues, "
     "ver pull requests abiertos y leer archivos de un repo remoto."),
    ("rag", "agents.rag_agent:get_rag_agent",
     "Documentos del usuario en data/documents (PDF, manuales, contratos). Úsalo para indexarlos o para "
     "responder 'según mis documentos'. Para notas de Obsidian usa las herramientas de Obsidian."),
    ("obsidian", "agents.obsidian_agent:get_obsidian_agent",
     "Notas de Obsidian. Úsalo para crear, leer, editar, añadir texto o buscar una nota concreta en el "
     "vault del usuario."),
    ("brain", "agents.brain_agent:get_brain_agent",
     "Segundo cerebro. Úsalo cuando el usuario pida analizar sus notas recientes y obtener insights, "
     "conclusiones o un resumen semanal de lo que escribió."),
    ("morning_briefing", "agents.morning_briefing_agent:get_morning_briefing_agent",
     "Briefing diario. Úsalo cuando el usuario pida el reporte o resumen de la mañana o del día: clima, "
     "calendario, correos, noticias y tareas en un solo informe."),
    ("skillforge", "agents.skillforge_agent:get_skillforge_agent",
     "Crea herramientas nuevas y permanentes. Úsalo cuando el usuario pida crear o guardar una skill o "
     "herramienta para reutilizarla después."),
    ("mcp_agent", "agents.mcp_agent:get_mcp_agent",
     "Git en el repositorio LOCAL. Úsalo para commits, ramas, diffs, estado de cambios, push y crear "
     "Pull Requests desde la rama actual. Pásale los detalles exactos (mensaje de commit, nombre de "
     "rama, body del PR). Push y merge requieren aprobación humana."),
]


def tool_name(agent: str) -> str:
    """Nombre de la tool del orquestador para un subagente (mcp_agent -> ..._mcp_agent)."""
    return f"orchestrator_consult_{agent}" if agent.endswith("_agent") else f"orchestrator_consult_{agent}_agent"


def _lazy_getter(target: str) -> Callable[[], Any]:
    module_name, attr = target.split(":")
    return lambda: getattr(importlib.import_module(module_name), attr)()


def _make_consult_tool(agent: str, target: str, description: str) -> BaseTool:
    getter = _lazy_getter(target)

    def consult(task: str) -> str:
        # ensure_config() returns this tool run's child config; passing it on keeps the
        # sub-agent's trace nested under the orchestrator even though it runs in another thread.
        return invoke_subagent(agent, getter, task, parent_config=ensure_config())

    return StructuredTool.from_function(func=consult, name=tool_name(agent), description=description)


@tool
def find_real_leads(query: str, platforms: str = "Upwork,Reddit", min_score: int = 7) -> str:
    """Busca ofertas de trabajo y clientes REALES usando un scraper. Úsala cuando el usuario pida:
    'buscar leads', 'buscar clientes', 'scraping de Upwork', 'scraping de Reddit',
    'buscar trabajos reales', 'oportunidades de trabajo reales' o similares.
    Devuelve URLs reales con propuestas personalizadas. NO usa DuckDuckGo ni búsqueda web.
    Parámetros: query = términos de búsqueda, platforms = plataformas separadas por coma (Upwork/Reddit/LinkedIn),
    min_score = calidad mínima del lead (1-10, default 7).
    """
    from agents.marketing_tools import marketing_scrape_leads

    plats = [p.strip() for p in platforms.split(",")]
    a2a_log("orchestrator", "lead_scraper", "find_real_leads", f"query={query} platforms={plats} min_score={min_score}")
    return marketing_scrape_leads.invoke({"query": query, "platforms": plats, "min_score": min_score})


def load_dynamic_tools() -> list[BaseTool]:
    """Tools autogeneradas por SkillForge en agents/dynamic_tools.py (recargadas en cada build)."""
    try:
        import agents.dynamic_tools as dt

        importlib.reload(dt)
    except Exception:  # código generado por LLM: cualquier error no debe tumbar el orquestador
        log.exception("Error cargando tools dinámicas")
        a2a_log("orchestrator", "system", "dynamic_tools_error", "ver logs")
        return []
    return [obj for _, obj in inspect.getmembers(dt) if isinstance(obj, BaseTool)]


def _start_reminder_daemon() -> None:
    """Daemon de recordatorios WhatsApp (una vez por proceso). Opcional: requiere Playwright.
    AIFORGE_DISABLE_REMINDERS=1 lo desactiva (demos, grabaciones, tests)."""
    if os.environ.get("AIFORGE_DISABLE_REMINDERS", "").strip() == "1":
        return
    try:
        from agents.reminder_agent import start_reminder_daemon
    except ImportError:
        log.warning("Recordatorios WhatsApp desactivados (Playwright no disponible)", exc_info=True)
        return
    start_reminder_daemon()


def build_orchestrator_tools() -> list[BaseTool]:
    from agents.rag_tools import rag_index_obsidian_vault, rag_query_obsidian

    _start_reminder_daemon()
    tools = [_make_consult_tool(*row) for row in SUBAGENTS]
    tools += [find_real_leads, rag_query_obsidian, rag_index_obsidian_vault]
    return tools + load_dynamic_tools()
