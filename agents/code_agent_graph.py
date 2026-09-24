"""Grafo LangGraph independiente: agente de código."""

from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from agents.agent_base import AgentBase
from agents.code_tools import build_code_tools
from agents.llm import get_llm
from agents.message_utils import extract_final_ai_text

CODE_PROMPT = """Eres el agente de CÓDIGO Python.
- Usa code_generate_and_execute para tareas de programación y ver la salida de ejecución.
- Si el usuario pide guardar el resultado o un recordatorio relacionado con el código, usa code_handoff_to_memory_agent.
Responde en español."""


class CodeAgent(AgentBase):
    @property
    def name(self) -> str:
        return "code"
        
    def __init__(self):
        self._graph = create_react_agent(
            get_llm(temperature=0.12),
            tools=build_code_tools(),
            prompt=CODE_PROMPT,
            name="code_agent",
        )
        
    def _run(self, user_input: str, context: Dict[str, Any], config: Dict[str, Any] | None) -> str:
        result = self._graph.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config or {"recursion_limit": 35},
        )
        return extract_final_ai_text(result) or "(sin respuesta)"


_CODE_AGENT: Any = None


def get_code_agent() -> CodeAgent:
    global _CODE_AGENT
    if _CODE_AGENT is None:
        _CODE_AGENT = CodeAgent()
    return _CODE_AGENT
