"""MorningBriefingAgent — Agente inteligente que consolida y prioriza tu día al encender el PC."""

from __future__ import annotations

from typing import Any, Dict
from datetime import datetime

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from agents.agent_base import AgentBase
from agents.llm import get_llm
from agents.morning_briefing_tools import get_briefing_tools
from agents.message_utils import extract_final_ai_text

BRIEFING_PROMPT = """Eres el AGENTE DE MORNING BRIEFING (MorningBriefingAgent) del usuario.
Tu objetivo es recopilar toda la información del día del usuario, estructurarla, priorizarla de forma inteligente y redactar un informe matutino consolidado, coherente y sumamente práctico.

DEBES usar las herramientas a tu disposición en secuencia para recabar la información completa:
1. `briefing_health_check`: Comprueba si Ollama, ChromaDB y FastMCP están saludables.
2. `briefing_get_daily_note_tasks`: Lee la Daily Note de hoy en Obsidian y extrae sus tareas.
3. `briefing_get_past_pending_tasks`: Trae las tareas incompletas de los últimos 3 días.
4. `briefing_get_projects_context`: Consulta el vault con RAG para saber en qué proyectos activos está trabajando el usuario.
5. `briefing_get_calendar_events`: Obtiene la agenda de hoy en Google Calendar.
6. `briefing_get_critical_emails`: Obtiene los correos importantes recibidos hoy en Gmail.
7. `briefing_get_weather_briefing`: Obtiene el reporte del clima de Bogotá con consejos prácticos.
8. `briefing_get_rss_news`: Obtiene los titulares recientes de HuggingFace, Papers with Code y TechCrunch AI.

INSTRUCCIONES DE SÍNTESIS Y REDACCIÓN:
1. **Foco del día:** Empieza con un bloque de 2-3 líneas de "Foco del día" con alta dosis de criterio. Analiza las tareas, eventos y el contexto de proyectos para deducir qué es lo verdaderamente crítico hoy y por qué.
2. **Priorización inteligente:** No te limites a copiar y pegar las tareas del día. Priorízalas por orden de impacto y urgencia considerando el contexto de proyectos activos obtenido.
3. **Estructura del Briefing:** Sigue estrictamente este orden de secciones en tu respuesta final:
   ---
   # 🌅 Morning Briefing — [Fecha Actual]
   
   ### 🎯 Foco del Día
   [2-3 líneas analíticas y de priorización estratégica]
   
   ### 📝 Tareas del Día (Priorizadas)
   [Lista priorizada de tareas de la nota diaria de hoy con checkboxes]
   
   ### ⏳ Pendientes de días anteriores
   [Lista de tareas que quedaron pendientes de los últimos 3 días]
   
   ### 📅 Agenda
   [Eventos de Google Calendar de hoy con comentarios prácticos]
   
   ### 🌦️ Clima y Consejos
   [Resumen del clima en Bogotá con tus recomendaciones sobre vestimenta/salidas]
   
   ### 📧 Correos Críticos
   [Resumen analítico de correos de Gmail filtrados que requieren acción hoy]
   
   ### 📰 Noticias del Sector (AI/Tech)
   [Breve resumen con 2-3 viñetas con enlaces de HuggingFace, Papers with Code, TechCrunch, etc.]
   
   ### 🛡️ Health Check del Sistema
   [Estado actual del stack AI-Forge]
   ---
4. **Tono y Lenguaje:** Tono directo, analítico, profesional, sin saludos genéricos ni fluff ("Hola", "Espero que tengas un buen día" están PROHIBIDOS). Debe leerse en 2-3 minutos.
5. **Idioma:** Español.

Llama a todas las herramientas necesarias de forma asertiva antes de redactar tu reporte final."""

class MorningBriefingAgent(AgentBase):
    @property
    def name(self) -> str:
        return "morning_briefing"

    def __init__(self):
        super().__init__()
        self._graph = create_react_agent(
            get_llm(temperature=0.2),
            tools=get_briefing_tools(),
            prompt=BRIEFING_PROMPT,
            name="morning_briefing_agent",
        )

    def _run(self, user_input: str, context: Dict[str, Any], config: Dict[str, Any] | None) -> str:
        # Enriquecer la entrada con la fecha y hora actual para evitar alucinaciones temporales
        current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        enriched_input = f"[Fecha y hora actual del sistema: {current_datetime}]\nInstrucción: {user_input}"
        
        result = self._graph.invoke(
            {"messages": [HumanMessage(content=enriched_input)]},
            config=config or {"recursion_limit": 40},
        )
        return extract_final_ai_text(result) or "(sin respuesta del agente de briefing)"

_MORNING_BRIEFING_AGENT: Any = None

def get_morning_briefing_agent() -> MorningBriefingAgent:
    global _MORNING_BRIEFING_AGENT
    if _MORNING_BRIEFING_AGENT is None:
        _MORNING_BRIEFING_AGENT = MorningBriefingAgent()
    return _MORNING_BRIEFING_AGENT
