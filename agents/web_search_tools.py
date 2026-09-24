"""Tools del agente de búsqueda web (incluye delegación A2A a memoria)."""

from __future__ import annotations

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from agents.a2a_log import a2a_log
from agents.message_utils import extract_final_ai_text
from agents.web_search import search_web


def build_web_search_tools():
    """Factory: evita import circular con memory_agent."""

    @tool
    def web_search_duckduckgo(query: str) -> str:
        """Busca información actual en internet (DuckDuckGo). query: términos o pregunta concisa."""
        a2a_log("web_search", "duckduckgo", "text_search", query)
        return search_web(query)

    @tool
    def web_search_save_findings_to_memory(instruction: str) -> str:
        """
        Delega en el agente de MEMORIA para guardar hallazgos, resúmenes o recordatorios.
        instruction: texto en español, p.ej. 'Añade progreso: hallazgos sobre X: ...'
        o 'Guarda recordatorio: revisar fuente Y'.
        """
        from agents.memory_agent import get_memory_agent

        a2a_log("web_search", "memory", "invoke_memory_agent_graph", instruction)
        agent = get_memory_agent()
        result = agent.invoke(
            {"messages": [HumanMessage(content=instruction)]},
            config={"recursion_limit": 25},
        )
        return extract_final_ai_text(result)

    return [web_search_duckduckgo, web_search_save_findings_to_memory]
