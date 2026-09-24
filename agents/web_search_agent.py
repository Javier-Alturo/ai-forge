"""Grafo LangGraph independiente: agente de búsqueda web con A2A a memoria."""

from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import HumanMessage
from agents.agent_base import AgentBase
from agents.message_utils import extract_final_ai_text

from langgraph.prebuilt import create_react_agent

from agents.llm import get_llm
from agents.web_search_tools import build_web_search_tools

WEB_PROMPT = """Eres el agente de BÚSQUEDA WEB.
- Usa web_search_duckduckgo para obtener información actualizada de internet.
- Si el usuario (o el orquestador) pide guardar hallazgos, fuentes o recordatorios derivados de la búsqueda,
  usa web_search_save_findings_to_memory con una instrucción clara en español para el agente de memoria.
Responde en español con síntesis útil y menciona URLs o títulos cuando proceda."""


class WebSearchAgent(AgentBase):
    @property
    def name(self) -> str:
        return "websearch"
        
    def __init__(self):
        self._graph = create_react_agent(
            get_llm(temperature=0.15),
            tools=build_web_search_tools(),
            prompt=WEB_PROMPT,
            name="web_search_agent",
        )
        
    def _run(self, user_input: str, context: Dict[str, Any], config: Dict[str, Any] | None) -> str:
        result = self._graph.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config or {"recursion_limit": 35},
        )
        return extract_final_ai_text(result) or "(sin respuesta)"

_WEB_AGENT: Any = None

def get_web_search_agent() -> WebSearchAgent:
    global _WEB_AGENT
    if _WEB_AGENT is None:
        _WEB_AGENT = WebSearchAgent()
    return _WEB_AGENT
