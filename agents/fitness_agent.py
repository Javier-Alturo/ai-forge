"""Grafo LangGraph independiente: agente de fitness (entrenamiento + seguimiento)."""

from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import HumanMessage
from agents.agent_base import AgentBase
from agents.message_utils import extract_final_ai_text

from langgraph.prebuilt import create_react_agent

from agents.fitness_tools import get_fitness_tools
from agents.llm import get_llm

FITNESS_PROMPT = """Eres el agente de FITNESS.

Contexto del atleta (edita estos valores con tus datos):
- Nombre: <tu nombre>
- Edad: <edad>
- Altura: <cm>
- Peso: <kg>
- Rutina: PPL×2 (Push/Pull/Legs) con énfasis alternado Fuerza/Hipertrofia por sesión
- Zonas protegidas: <lesiones o zonas a cuidar>
- Última sesión conocida: <se lee del historial con fitness_get_history>
- Próxima sesión objetivo: <se calcula con fitness_next_session>

Reglas de trabajo:
- Prioriza consistencia, técnica, y gestión de fatiga (RIR) sobre “subir por subir”.
- Si el usuario pide registrar entreno, usa fitness_log_session con datos estructurados.
- Para “qué toca hoy”, usa fitness_next_session (basado en historial y perfil).
- Para ver progreso, usa fitness_get_history, fitness_check_prs y fitness_weekly_report.
- Si hay molestias, registra con fitness_injury_log y adapta el plan (ejercicios más amigables, menor volumen/intensidad).

Responde en español, claro y accionable."""


class FitnessAgent(AgentBase):
    @property
    def name(self) -> str:
        return "fitness"
        
    def __init__(self):
        self._graph = create_react_agent(
            get_llm(temperature=0.15),
            tools=get_fitness_tools(),
            prompt=FITNESS_PROMPT,
            name="fitness_agent",
        )
        
    def _run(self, user_input: str, context: Dict[str, Any], config: Dict[str, Any] | None) -> str:
        result = self._graph.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config or {"recursion_limit": 35},
        )
        return extract_final_ai_text(result) or "(sin respuesta)"

_FITNESS_AGENT: Any = None

def get_fitness_agent() -> FitnessAgent:
    global _FITNESS_AGENT
    if _FITNESS_AGENT is None:
        _FITNESS_AGENT = FitnessAgent()
    return _FITNESS_AGENT

