"""Grafo LangGraph: agente de Google Calendar."""

from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import HumanMessage
from agents.agent_base import AgentBase
from agents.message_utils import extract_final_ai_text

from langgraph.prebuilt import create_react_agent

from agents.calendar_tools import get_calendar_tools
from agents.llm import get_llm

CAL_PROMPT = """Eres el agente de CALENDARIO (Google Calendar).
Lista, crea, borra o busca eventos usando las herramientas. Mismas credenciales OAuth que Gmail.
Fechas en ISO8601 con zona horaria. Responde en español."""


class CalendarAgent(AgentBase):
    @property
    def name(self) -> str:
        return "calendar"
        
    def __init__(self):
        self._graph = create_react_agent(
            get_llm(temperature=0.1),
            tools=get_calendar_tools(),
            prompt=CAL_PROMPT,
            name="calendar_agent",
        )
        
    def _run(self, user_input: str, context: Dict[str, Any], config: Dict[str, Any] | None) -> str:
        result = self._graph.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config or {"recursion_limit": 35},
        )
        return extract_final_ai_text(result) or "(sin respuesta)"

_CAL_AGENT: Any = None

def get_calendar_agent() -> CalendarAgent:
    global _CAL_AGENT
    if _CAL_AGENT is None:
        _CAL_AGENT = CalendarAgent()
    return _CAL_AGENT
