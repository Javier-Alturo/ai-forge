"""Tools the orchestrator can call: one per sub-agent, plus direct RAG/lead tools and
SkillForge-generated dynamic tools.

Sub-agent tools are generated from SUBAGENTS (a data table) instead of one
hand-written function each; tool names and descriptions are unchanged.
"""

from __future__ import annotations

import importlib
import inspect
from typing import Any, Callable

from langchain_core.runnables.config import ensure_config
from langchain_core.tools import BaseTool, StructuredTool, tool

from agents.a2a_log import a2a_log
from agents.logger import get_logger
from agents.subagent_runner import invoke_subagent

log = get_logger("orchestrator")

# (registry name, "module:getter", tool description)
SUBAGENTS: list[tuple[str, str, str]] = [
    ("web_search", "agents.web_search_agent:get_web_search_agent",
     "Delega en el agente de búsqueda web (DuckDuckGo; puede guardar hallazgos en memoria)."),
    ("memory", "agents.memory_agent:get_memory_agent",
     "Delega en el agente de memoria ChromaDB + embeddings (recordatorios, búsqueda semántica)."),
    ("code", "agents.code_agent_graph:get_code_agent",
     "Delega en el agente de código Python (generar y ejecutar; opcional memoria)."),
    ("neural_network", "agents.neural_network_agent:get_neural_network_agent",
     "Delega en el agente de redes neuronales PyTorch (diseño, código, entrenamiento, guardar métricas en memoria)."),
    ("fitness", "agents.fitness_agent:get_fitness_agent",
     "Delega en el agente de fitness (sesiones, PRs, historial, lesiones, reporte semanal)."),
    ("taskforge", "agents.taskforge_agent:get_taskforge_agent",
     "Delega en el agente TaskForge: tareas del dia, metas a largo plazo, habitos, recordatorios por WhatsApp "
     "y metricas de productividad."),
    ("marketing", "agents.marketing_agent:get_marketing_agent",
     "Delega en el agente de marketing (buscar clientes/leads reales con scraper, research, contenido, "
     "propuestas, outreach)."),
    ("file", "agents.file_agent:get_file_agent",
     "Delega en el agente de archivos del sistema (leer, escribir, listar, mover/copiar, buscar)."),
    ("email", "agents.email_agent:get_email_agent",
     "Delega en el agente de Gmail en solo lectura (listar y buscar correos; OAuth2)."),
    ("calendar", "agents.calendar_agent:get_calendar_agent",
     "Delega en el agente de Google Calendar (mismas credenciales OAuth que Gmail)."),
    ("voice", "agents.voice_agent:get_voice_agent",
     "Delega en el agente de voz (micrófono + Whisper local)."),
    ("image", "agents.image_agent:get_image_agent",
     "Delega en el agente de imágenes Stable Diffusion (diffusers, CUDA recomendada)."),
    ("computer_use", "agents.computer_use_agent:get_computer_use_agent",
     "Delega en computer use: captura de pantalla, clic, teclado, mouse, abrir apps (PyAutoGUI + llava)."),
    ("github", "agents.github_agent:get_github_agent",
     "Delega en GitHub: repos, archivos, issues, PRs (requiere GITHUB_TOKEN)."),
    ("rag", "agents.rag_agent:get_rag_agent",
     "Delega en RAG: indexar/consultar documentos en data/documents/ (LlamaIndex + Chroma)."),
    ("obsidian", "agents.obsidian_agent:get_obsidian_agent",
     "Delega en el agente de Obsidian (leer, escribir, añadir, buscar notas Markdown en el vault)."),
    ("brain", "agents.brain_agent:get_brain_agent",
     "Delega en el agente Cerebro. Ejecuta revisiones automáticas de notas recientes y genera insights "
     "o reportes semanales."),
    ("morning_briefing", "agents.morning_briefing_agent:get_morning_briefing_agent",
     "Delega en el agente de Morning Briefing. Genera un reporte completo diario recopilando clima, calendario, "
     "correos, noticias RSS, tareas pendientes y contexto de proyectos."),
    ("skillforge", "agents.skillforge_agent:get_skillforge_agent",
     "Delega en el agente SkillForge (Creador de Habilidades). Úsalo cuando necesites programar y guardar una "
     "nueva herramienta o skill permanente."),
    ("mcp_agent", "agents.mcp_agent:get_mcp_agent",
     "Delega en el agente MCP especializado. Úsalo EXCLUSIVAMENTE para interactuar con el control de versiones "
     "y repositorios: hacer commits, push, revisar diffs, listar ramas y crear Pull Requests en GitHub. Pásale "
     "todos los detalles técnicos exactos (mensajes de commit, nombres de ramas, body del PR). "
     "Push y merge requieren aprobación humana."),
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
    """Daemon de recordatorios WhatsApp (una vez por proceso). Opcional: requiere Playwright."""
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
