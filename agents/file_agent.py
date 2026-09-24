"""Grafo LangGraph: agente de archivos del sistema."""

from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import HumanMessage
from agents.agent_base import AgentBase
from agents.message_utils import extract_final_ai_text

from langgraph.prebuilt import create_react_agent

from agents.file_tools import get_file_tools
from agents.llm import get_llm

FILE_PROMPT = """Eres el agente de ARCHIVOS del sistema.
Puedes leer, escribir, listar directorios, mover/copiar y buscar archivos en cualquier ruta que el usuario indique.
Usa las herramientas con rutas exactas. Responde en español, con precaución: operaciones destructivas (sobrescribir, mover) son irreversibles.
Si falta información (ruta, contenido), pide aclaración."""


class FileAgent(AgentBase):
    @property
    def name(self) -> str:
        return "file"
        
    def __init__(self):
        self._graph = create_react_agent(
            get_llm(temperature=0.1),
            tools=get_file_tools(),
            prompt=FILE_PROMPT,
            name="file_agent",
        )
        
    def _run(self, user_input: str, context: Dict[str, Any], config: Dict[str, Any] | None) -> str:
        result = self._graph.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config or {"recursion_limit": 35},
        )
        return extract_final_ai_text(result) or "(sin respuesta)"

_FILE_AGENT: Any = None

def get_file_agent() -> FileAgent:
    global _FILE_AGENT
    if _FILE_AGENT is None:
        _FILE_AGENT = FileAgent()
    return _FILE_AGENT
