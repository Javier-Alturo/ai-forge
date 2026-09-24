"""Grafo LangGraph: agente de voz (micrófono + Whisper)."""

from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import HumanMessage
from agents.agent_base import AgentBase
from agents.message_utils import extract_final_ai_text

from langgraph.prebuilt import create_react_agent

from agents.llm import get_llm
from agents.voice_tools import get_voice_tools, record_and_transcribe_impl

VOICE_PROMPT = """Eres el agente de VOZ.
Usa voice_record_and_transcribe para capturar audio del micrófono hasta silencio y obtener texto con Whisper local.
Responde en español con la transcripción y un breve resumen si aplica."""


class VoiceAgent(AgentBase):
    @property
    def name(self) -> str:
        return "voice"
        
    def __init__(self):
        self._graph = create_react_agent(
            get_llm(temperature=0.1),
            tools=get_voice_tools(),
            prompt=VOICE_PROMPT,
            name="voice_agent",
        )
        
    def _run(self, user_input: str, context: Dict[str, Any], config: Dict[str, Any] | None) -> str:
        result = self._graph.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config or {"recursion_limit": 35},
        )
        return extract_final_ai_text(result) or "(sin respuesta)"

_VOICE_AGENT: Any = None

def get_voice_agent() -> VoiceAgent:
    global _VOICE_AGENT
    if _VOICE_AGENT is None:
        _VOICE_AGENT = VoiceAgent()
    return _VOICE_AGENT


def run_voice_cli_session() -> None:
    """
    Flujo CLI 'voz': graba, transcribe y envía el texto al orquestador (A2A).
    """
    from agents.orchestrator import run_turn

    print("Grabando… (habla; el silencio detiene la grabación)\n", flush=True)
    text = record_and_transcribe_impl()
    print(f"\nTranscripción:\n{text}\n", flush=True)
    if text.strip():
        msg = run_turn(f"Entrada por voz del usuario:\n{text}")
        print((msg.content or "") + "\n", flush=True)
