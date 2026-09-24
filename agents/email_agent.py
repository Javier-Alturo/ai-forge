"""Grafo LangGraph: agente de correo Gmail."""

from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import HumanMessage
from agents.agent_base import AgentBase
from agents.message_utils import extract_final_ai_text

from langgraph.prebuilt import create_react_agent

from agents.email_tools import get_email_tools
from agents.llm import get_llm

EMAIL_PROMPT = """Eres el agente de CORREO (Gmail).
Usa las herramientas para listar, buscar o enviar emails. Requiere OAuth2 (credentials.json + token.json).
Responde en español. Para enviar, confirma destinatario y asunto si el usuario fue ambiguo."""


class EmailAgent(AgentBase):
    @property
    def name(self) -> str:
        return "email"
        
    def __init__(self):
        self._graph = create_react_agent(
            get_llm(temperature=0.1),
            tools=get_email_tools(),
            prompt=EMAIL_PROMPT,
            name="email_agent",
        )
        
    def _run(self, user_input: str, context: Dict[str, Any], config: Dict[str, Any] | None) -> str:
        result = self._graph.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config or {"recursion_limit": 35},
        )
        return extract_final_ai_text(result) or "(sin respuesta)"

_EMAIL_AGENT: Any = None

def get_email_agent() -> EmailAgent:
    global _EMAIL_AGENT
    if _EMAIL_AGENT is None:
        _EMAIL_AGENT = EmailAgent()
    return _EMAIL_AGENT
