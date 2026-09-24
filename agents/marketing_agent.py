"""Grafo LangGraph independiente: agente de marketing (clientes para IA/automatización)."""

from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from agents.agent_base import AgentBase
from agents.llm import get_llm
from agents.marketing_tools import get_marketing_tools
from agents.message_utils import extract_final_ai_text

MARKETING_PROMPT = """Eres el agente de MARKETING/VENTAS para conseguir clientes.

Perfil del usuario (edítalo con tu propia oferta):
- Servicios: automatizaciones con n8n, agentes IA con LangGraph, bots WhatsApp, integraciones API
- Mercado: clientes internacionales vía Upwork + LinkedIn
- Diferenciador: sistemas multi-agente A2A, opción de LLMs locales, expertise técnico real

Reglas:
- Piensa en términos de oferta (resultado), nicho, prueba, y CTA.
- Si investigas estrategias, usa marketing_research_clients / marketing_analyze_competitor y guarda lo útil.
- **REGLA DE ORO: NUNCA inventes nombres de clientes, trabajos ni URLs (no alucines).**
- **Para buscar leads reales:** DEBES usar la herramienta `marketing_scrape_leads(query, platforms, min_score)`. Esta herramienta automáticamente leerá las ofertas, las calificará, descartará la basura, y generará las propuestas usando el RAG del perfil del usuario.
- TU ÚNICO TRABAJO después de usar el scraper es mostrarle al usuario de forma limpia los resultados que te devolvió la herramienta, asegurándote de imprimir SIEMPRE el Link/URL real para que el usuario pueda darle clic y aplicar.
- **REGLA CRÍTICA:** Si la herramienta `marketing_scrape_leads` no devuelve leads (porque no había hoy), responde EXACTAMENTE: "No encontré leads relevantes hoy en [plataformas]. Intenta mañana o amplía el query." NO generes calendarios ni content como fallback cuando se te pida buscar leads. Eso confunde al usuario.

Responde en español salvo la propuesta final (que suele ser en inglés)."""


class MarketingAgent(AgentBase):
    @property
    def name(self) -> str:
        return "marketing"
        
    def __init__(self):
        self._graph = create_react_agent(
            get_llm(temperature=0.2),
            tools=get_marketing_tools(),
            prompt=MARKETING_PROMPT,
            name="marketing_agent",
        )
        
    def _run(self, user_input: str, context: Dict[str, Any], config: Dict[str, Any] | None) -> str:
        result = self._graph.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config or {"recursion_limit": 35},
        )
        return extract_final_ai_text(result) or "(sin respuesta)"


_MARKETING_AGENT: Any = None


def get_marketing_agent() -> MarketingAgent:
    global _MARKETING_AGENT
    if _MARKETING_AGENT is None:
        _MARKETING_AGENT = MarketingAgent()
    return _MARKETING_AGENT
