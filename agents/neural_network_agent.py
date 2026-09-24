"""Grafo LangGraph independiente: agente de redes neuronales (PyTorch)."""

from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import HumanMessage
from agents.agent_base import AgentBase
from agents.message_utils import extract_final_ai_text

from langgraph.prebuilt import create_react_agent

from agents.llm import get_llm
from agents.neural_network_tools import build_neural_network_tools

NN_PROMPT = """Eres el agente de REDES NEURONALES (PyTorch).

IMPORTANTE: LangGraph puede ejecutar varias herramientas en paralelo si las pides en el mismo turno.
Para diseño+generación+ejecución+guardar métricas, usa UNA sola herramienta: nn_run_sequential_training_pipeline
(salvo que el usuario pida solo diseño o solo código sin ejecutar).

Herramientas puntuales (un solo paso por turno cuando las uses):
- nn_design_architecture
- nn_generate_pytorch_training_code (tras tener un diseño o resumen)
- nn_run_training_script (solo si ya tienes el código final)
- nn_save_training_progress_to_memory (solo con métricas reales ya obtenidas)

Responde en español."""


class NeuralNetworkAgent(AgentBase):
    @property
    def name(self) -> str:
        return "neuralnetwork"
        
    def __init__(self):
        self._graph = create_react_agent(
            get_llm(temperature=0.18),
            tools=build_neural_network_tools(),
            prompt=NN_PROMPT,
            name="neural_network_agent",
        )
        
    def _run(self, user_input: str, context: Dict[str, Any], config: Dict[str, Any] | None) -> str:
        result = self._graph.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config or {"recursion_limit": 35},
        )
        return extract_final_ai_text(result) or "(sin respuesta)"

_NN_AGENT: Any = None

def get_neural_network_agent() -> NeuralNetworkAgent:
    global _NN_AGENT
    if _NN_AGENT is None:
        _NN_AGENT = NeuralNetworkAgent()
    return _NN_AGENT
