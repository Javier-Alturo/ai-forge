"""Grafo LangGraph: agente de Obsidian."""

from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import HumanMessage
from agents.agent_base import AgentBase
from agents.message_utils import extract_final_ai_text

from langgraph.prebuilt import create_react_agent

from agents.obsidian_tools import get_obsidian_tools
from agents.llm import get_llm

OBSIDIAN_PROMPT = """Eres el agente de OBSIDIAN del sistema.
Gestionas el personal knowledge management (PKM) del usuario interactuando con su vault local.
Puedes leer, escribir, añadir (append) y buscar notas en formato Markdown.
Cuando crees notas, usa sintaxis Markdown adecuada (encabezados, listas) y si es útil, usa enlaces bidireccionales de Obsidian (ejemplo: [[Nombre de otra nota]]).
Responde en español de forma concisa. 
Si obtienes un error porque el vault no está configurado, indícale amablemente al usuario que debe añadir la variable OBSIDIAN_VAULT_PATH en su archivo .env."""

class ObsidianAgent(AgentBase):
    @property
    def name(self) -> str:
        return "obsidian"
        
    def __init__(self):
        self._graph = create_react_agent(
            get_llm(temperature=0.2),
            tools=get_obsidian_tools(),
            prompt=OBSIDIAN_PROMPT,
            name="obsidian_agent",
        )
        
    def _run(self, user_input: str, context: Dict[str, Any], config: Dict[str, Any] | None) -> str:
        result = self._graph.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config or {"recursion_limit": 35},
        )
        return extract_final_ai_text(result) or "(sin respuesta)"

_OBSIDIAN_AGENT: Any = None

def get_obsidian_agent() -> ObsidianAgent:
    global _OBSIDIAN_AGENT
    if _OBSIDIAN_AGENT is None:
        _OBSIDIAN_AGENT = ObsidianAgent()
    return _OBSIDIAN_AGENT
