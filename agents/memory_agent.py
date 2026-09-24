"""Grafo LangGraph independiente: agente de memoria (ReAct + tools)."""

from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from agents.agent_base import AgentBase
from agents.llm import get_llm
from agents.memory_tools import get_memory_tools
from agents.message_utils import extract_final_ai_text

MEMORY_PROMPT = """Eres el agente de MEMORIA (ChromaDB + embeddings locales all-MiniLM-L6-v2).
Puedes listar, crear y borrar recordatorios y progreso; buscar con memory_semantic_search; guardar notas con embedding
(memory_add_embedding); recuperar contexto relevante con memory_get_context.
Responde en español, breve y claro. No inventes ids: usa los que devuelven las herramientas."""


class MemoryAgent(AgentBase):
    @property
    def name(self) -> str:
        return "memory"
        
    def __init__(self):
        self._graph = create_react_agent(
            get_llm(temperature=0.1),
            tools=get_memory_tools(),
            prompt=MEMORY_PROMPT,
            name="memory_agent",
        )
        
    def _run(self, user_input: str, context: Dict[str, Any], config: Dict[str, Any] | None) -> str:
        result = self._graph.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config or {"recursion_limit": 35},
        )
        return extract_final_ai_text(result) or "(sin respuesta)"


_MEMORY_AGENT: Any = None


def get_memory_agent() -> MemoryAgent:
    global _MEMORY_AGENT
    if _MEMORY_AGENT is None:
        _MEMORY_AGENT = MemoryAgent()
    return _MEMORY_AGENT
