"""Grafo LangGraph independiente: Agente MCP (Gestor Especializado de Repositorio y Entorno)."""

from __future__ import annotations

from typing import Any, Dict
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from agents.agent_base import AgentBase
from agents.llm import get_llm
from agents.mcp_client import load_mcp_tools
from agents.message_utils import extract_final_ai_text
from agents.a2a_log import a2a_log

MCP_PROMPT = """Eres el MCP AGENT (Gestor de Repositorio) de AI-Forge.
Tu responsabilidad exclusiva es administrar el control de versiones local e interacciones con el repositorio usando las herramientas del servidor MCP que tienes cargadas en memoria.

Tienes acceso a herramientas como:
- aiforge_commit_push: Para hacer commits de cambios locales y empujarlos a ramas.
- aiforge_create_pr: Para abrir un Pull Request en GitHub.
- aiforge_list_branches: Para listar ramas.
- aiforge_get_diff: Para revisar cambios no confirmados.

Instrucciones:
1. El usuario (o el Orquestador) te pedirá que realices tareas de Git/GitHub (commits, creación de ramas, PRs).
2. Usa directamente tus herramientas MCP para ejecutar la tarea. Si te piden hacer un commit y un PR, invoca las herramientas secuencialmente.
3. Si alguna herramienta MCP te pide parámetros específicos (como `title`, `base_branch`, `head_branch`, `body`), asegúrate de llenarlos correctamente según las instrucciones recibidas.
4. Responde en español confirmando de forma breve qué herramientas utilizaste y el resultado o URL generada.

NOTA: Estás en un entorno de agente independiente aislado, diseñado para evitar la sobrecarga cognitiva, por lo tanto tienes plena capacidad y libertad para usar estas herramientas complejas."""

class McpAgent(AgentBase):
    @property
    def name(self) -> str:
        return "mcp_agent"
        
    def __init__(self):
        tools = load_mcp_tools()
        if not tools:
            a2a_log("mcp_agent", "system", "warning", "No se encontraron herramientas MCP para cargar en el agente.")
            
        self._graph = create_react_agent(
            get_llm(temperature=0.1),
            tools=tools,
            prompt=MCP_PROMPT,
            name="mcp_agent",
        )
        
    def _run(self, user_input: str, context: Dict[str, Any], config: Dict[str, Any] | None) -> str:
        result = self._graph.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config or {"recursion_limit": 20},
        )
        return extract_final_ai_text(result) or "(sin respuesta)"

_MCP_AGENT: Any = None

def get_mcp_agent() -> McpAgent:
    global _MCP_AGENT
    if _MCP_AGENT is None:
        _MCP_AGENT = McpAgent()
    return _MCP_AGENT
