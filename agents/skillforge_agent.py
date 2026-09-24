"""Grafo LangGraph independiente: Agente SkillForge (Creador de Habilidades)."""

from __future__ import annotations

from typing import Any, Dict
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from agents.agent_base import AgentBase
from agents.llm import get_llm
from agents.skillforge_tools import get_skillforge_tools
from agents.code_tools import build_code_tools
from agents.message_utils import extract_final_ai_text

SKILLFORGE_PROMPT = """Eres el SKILLFORGE AGENT de AI-Forge. Tu único propósito es escribir, probar y guardar nuevas herramientas (skills) en código Python para expandir las capacidades del sistema.

Instrucciones:
1. El usuario te pedirá que crees una herramienta que haga X.
2. Escribe el código Python necesario. 
   - IMPORTANTE: La función principal DEBE estar decorada con `@tool` de `langchain_core.tools`.
   - DEBE tener docstrings claros explicando qué hace la herramienta y qué parámetros recibe.
   - Si usas librerías externas (como `requests`), asegúrate de importarlas dentro del código.
3. Utiliza la herramienta `code_generate_and_execute` para probar un pequeño snippet que demuestre que la lógica base funciona (opcional pero recomendado).
4. Usa la herramienta `skillforge_save_tool` enviándole ÚNICAMENTE el código final limpio (con los imports y el @tool) para guardarlo permanentemente.
5. Una vez guardado, dile al usuario que la herramienta ha sido creada y que reinicie el Orquestador o Dashboard para cargarla.

NO intentes responder a preguntas generales, concéntrate solo en programar la herramienta solicitada. Usa siempre español para comunicarte con el usuario, pero el código Python en inglés."""

class SkillForgeAgent(AgentBase):
    @property
    def name(self) -> str:
        return "skillforge"
        
    def __init__(self):
        # Combinamos tools: poder ejecutar código para probar + poder guardar el código.
        tools = [*get_skillforge_tools(), *build_code_tools()]
        
        self._graph = create_react_agent(
            get_llm(temperature=0.2),  # Baja temperatura para código preciso
            tools=tools,
            prompt=SKILLFORGE_PROMPT,
            name="skillforge_agent",
        )
        
    def _run(self, user_input: str, context: Dict[str, Any], config: Dict[str, Any] | None) -> str:
        result = self._graph.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config or {"recursion_limit": 30},
        )
        return extract_final_ai_text(result) or "(sin respuesta)"

_SKILLFORGE_AGENT: Any = None

def get_skillforge_agent() -> SkillForgeAgent:
    global _SKILLFORGE_AGENT
    if _SKILLFORGE_AGENT is None:
        _SKILLFORGE_AGENT = SkillForgeAgent()
    return _SKILLFORGE_AGENT
