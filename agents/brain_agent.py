"""Grafo LangGraph independiente: Agente Cerebro (Brain)."""

from __future__ import annotations

from typing import Any, Dict
from datetime import datetime

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from agents.agent_base import AgentBase
from agents.llm import get_llm
from agents.obsidian_tools import get_obsidian_tools
from agents.message_utils import extract_final_ai_text

BRAIN_PROMPT = """Eres el SEGUNDO CEREBRO AUTOMÁTICO del usuario (AI-Forge Brain Agent).
Tu objetivo es reflexionar sobre el conocimiento y actividad reciente del usuario.
El usuario te pedirá que generes una revisión o síntesis.
Debes:
1. Usar obsidian_get_recent_notes para leer las notas creadas o modificadas en los últimos días (ej. 7 días).
2. Analizar el contenido: detectar conexiones, ideas recurrentes, proyectos activos y temas clave.
3. Generar un documento estructurado de Insights / Reflexión.
4. Usar obsidian_write_note para guardar este documento en la carpeta 'Brain_Insights/' dentro del vault. 
El título de la nota debe ser 'Brain_Insights/Weekly Review YYYY-MM-DD.md' (reemplazando con la fecha actual).

Responde en español, usando un tono reflexivo y analítico, como un pensador o un estratega."""

class BrainAgent(AgentBase):
    @property
    def name(self) -> str:
        return "brain"
        
    def __init__(self):
        self._graph = create_react_agent(
            get_llm(temperature=0.3),
            tools=get_obsidian_tools(),
            prompt=BRAIN_PROMPT,
            name="brain_agent",
        )
        
    def _run(self, user_input: str, context: Dict[str, Any], config: Dict[str, Any] | None) -> str:
        # Añadir la fecha actual al contexto para que el LLM no se la invente
        current_date = datetime.now().strftime("%Y-%m-%d")
        enriched_input = f"[Fecha actual: {current_date}]\n{user_input}"
        
        result = self._graph.invoke(
            {"messages": [HumanMessage(content=enriched_input)]},
            config=config or {"recursion_limit": 40},
        )
        return extract_final_ai_text(result) or "(sin respuesta)"

_BRAIN_AGENT: Any = None

def get_brain_agent() -> BrainAgent:
    global _BRAIN_AGENT
    if _BRAIN_AGENT is None:
        _BRAIN_AGENT = BrainAgent()
    return _BRAIN_AGENT
