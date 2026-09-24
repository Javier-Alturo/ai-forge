"""Grafo LangGraph: agente GitHub (PyGithub)."""

from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import HumanMessage
from agents.agent_base import AgentBase
from agents.message_utils import extract_final_ai_text

from langgraph.prebuilt import create_react_agent

from agents.github_tools import get_github_tools
from agents.llm import get_llm

GH_PROMPT = """Eres el agente de GITHUB.
Usa las herramientas para listar repos, leer o escribir archivos, issues y pull requests.
Requiere GITHUB_TOKEN en el entorno. Responde en español; confirma nombres owner/repo antes de escrituras."""


class GithubAgent(AgentBase):
    @property
    def name(self) -> str:
        return "github"
        
    def __init__(self):
        self._graph = create_react_agent(
            get_llm(temperature=0.1),
            tools=get_github_tools(),
            prompt=GH_PROMPT,
            name="github_agent",
        )
        
    def _run(self, user_input: str, context: Dict[str, Any], config: Dict[str, Any] | None) -> str:
        result = self._graph.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config or {"recursion_limit": 35},
        )
        return extract_final_ai_text(result) or "(sin respuesta)"

_GH_AGENT: Any = None

def get_github_agent() -> GithubAgent:
    global _GH_AGENT
    if _GH_AGENT is None:
        _GH_AGENT = GithubAgent()
    return _GH_AGENT
