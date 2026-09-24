"""Grafo LangGraph: agente de generación de imágenes (Stable Diffusion)."""

from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import HumanMessage
from agents.agent_base import AgentBase
from agents.message_utils import extract_final_ai_text

from langgraph.prebuilt import create_react_agent

from agents.image_tools import get_image_tools
from agents.llm import get_llm

IMAGE_PROMPT = """Eres el agente de IMÁGENES (Stable Diffusion local con diffusers).
Genera imágenes con image_generate según el prompt del usuario; usa negative_prompt si conviene.
Las salidas van a la carpeta outputs del proyecto (configurable con IMAGE_OUTPUT_DIR).
Requiere GPU NVIDIA + CUDA para rendimiento razonable (p.ej. RTX 5070 Ti).
Responde en español con la ruta del archivo generado."""


class ImageAgent(AgentBase):
    @property
    def name(self) -> str:
        return "image"
        
    def __init__(self):
        self._graph = create_react_agent(
            get_llm(temperature=0.25),
            tools=get_image_tools(),
            prompt=IMAGE_PROMPT,
            name="image_agent",
        )
        
    def _run(self, user_input: str, context: Dict[str, Any], config: Dict[str, Any] | None) -> str:
        result = self._graph.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config or {"recursion_limit": 35},
        )
        return extract_final_ai_text(result) or "(sin respuesta)"

_IMG_AGENT: Any = None

def get_image_agent() -> ImageAgent:
    global _IMG_AGENT
    if _IMG_AGENT is None:
        _IMG_AGENT = ImageAgent()
    return _IMG_AGENT
