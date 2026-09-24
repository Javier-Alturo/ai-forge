"""Grafo LangGraph: RAG sobre documentos en data/documents/."""

from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from agents.agent_base import AgentBase
from agents.llm import get_llm
from agents.rag_tools import get_rag_tools
from agents.message_utils import extract_final_ai_text

RAG_PROMPT = """Eres el agente de DOCUMENTOS RAG (LlamaIndex + ChromaDB).
Los archivos fuente viven en data/documents/ (PDF, TXT, MD). Usa rag_index_documents tras añadir archivos,
rag_query para preguntas, rag_add_document para crear texto nuevo indexado, rag_list_indexed para inspeccionar la colección.
Responde en español."""


class RagAgent(AgentBase):
    @property
    def name(self) -> str:
        return "rag"
        
    def __init__(self):
        self._graph = create_react_agent(
            get_llm(temperature=0.15),
            tools=get_rag_tools(),
            prompt=RAG_PROMPT,
            name="rag_agent",
        )
        
    def _run(self, user_input: str, context: Dict[str, Any], config: Dict[str, Any] | None) -> str:
        result = self._graph.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config or {"recursion_limit": 35},
        )
        return extract_final_ai_text(result) or "(sin respuesta)"


_RAG_AGENT: Any = None


def get_rag_agent() -> RagAgent:
    global _RAG_AGENT
    if _RAG_AGENT is None:
        _RAG_AGENT = RagAgent()
    return _RAG_AGENT
