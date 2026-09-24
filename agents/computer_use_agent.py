"""Grafo LangGraph: control local del escritorio (PyAutoGUI + visión)."""

from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import HumanMessage
from agents.agent_base import AgentBase
from agents.message_utils import extract_final_ai_text

from langgraph.prebuilt import create_react_agent

from agents.computer_use_tools import get_computer_use_tools
from agents.llm import get_llm

CU_PROMPT = """Eres el agente de COMPUTER USE (control local del PC).
Usa las herramientas con extremo cuidado: clicks y escritura actúan en la máquina real del usuario.
Antes de acciones destructivas, pide confirmación implícita vía descripción clara.
Requiere Ollama con modelo de visión (p.ej. llava) para screenshot/detección. Responde en español."""


class ComputerUseAgent(AgentBase):
    @property
    def name(self) -> str:
        return "computeruse"
        
    def __init__(self):
        self._graph = create_react_agent(
            get_llm(temperature=0.1),
            tools=get_computer_use_tools(),
            prompt=CU_PROMPT,
            name="computer_use_agent",
        )
        
    def _run(self, user_input: str, context: Dict[str, Any], config: Dict[str, Any] | None) -> str:
        result = self._graph.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config or {"recursion_limit": 35},
        )
        return extract_final_ai_text(result) or "(sin respuesta)"

_CU_AGENT: Any = None

def get_computer_use_agent() -> ComputerUseAgent:
    global _CU_AGENT
    if _CU_AGENT is None:
        _CU_AGENT = ComputerUseAgent()
    return _CU_AGENT
