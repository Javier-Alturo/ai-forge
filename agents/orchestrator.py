"""Orquestador principal: grafo LangGraph ReAct que invoca otros agentes como tools (A2A)."""

from __future__ import annotations

import threading
import uuid
from typing import Any, AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.prebuilt import create_react_agent

from agents.a2a_log import a2a_log
from agents.llm import OLLAMA_BASE, OLLAMA_MODEL, get_llm
from agents.logger import get_logger, set_trace_id
from agents.message_utils import extract_final_ai_text
from agents.orchestrator_tools import build_orchestrator_tools
from agents.subagent_runner import get_model_router, invoke_subagent

# Alias de compatibilidad (tests y código antiguo usan los nombres privados)
_invoke_subagent = invoke_subagent
_get_model_router = get_model_router

# Re-export para main.py
__all__ = [
    "OLLAMA_BASE",
    "OLLAMA_MODEL",
    "arun_turn_stream",
    "build_orchestrator_tools",
    "get_orchestrator_graph",
    "run_turn",
]

_ORCHESTRATOR: Any = None
# Checkpointer en memoria: mantiene historial de conversación por thread_id durante la sesión.
# Para persistencia entre reinicios, sustituir por SqliteSaver (langgraph-checkpoint-sqlite).
_CHECKPOINTER = MemorySaver()
log = get_logger("orchestrator")

ORCH_PROMPT = """Eres el ORQUESTADOR principal del sistema multi-agente (A2A con LangGraph).
Responde al usuario en español.

Herramientas internas (cada una invoca un grafo agente independiente):
- orchestrator_consult_web_search_agent: información actual en internet, noticias, verificación externa.
- orchestrator_consult_memory_agent: memoria persistente ChromaDB + embeddings (recordatorios, búsqueda semántica).
- orchestrator_consult_code_agent: código Python general (stdlib por defecto), ejecución local.
- orchestrator_consult_neural_network_agent: diseño de redes, código PyTorch, entrenamiento breve en CPU, métricas.
- orchestrator_consult_fitness_agent: seguimiento de entrenamiento (PPL), PRs, sesiones, molestias, reportes semanales.
- orchestrator_consult_taskforge_agent: sistema de productividad personal del usuario — tareas del dia, metas a largo plazo (ej: ingles B2), habitos diarios, recordatorios, metricas semanales e historial. USAR SIEMPRE para cualquier peticion sobre tareas, metas, habitos, recordatorios o productividad.
- orchestrator_consult_marketing_agent: USAR SIEMPRE para buscar clientes/leads/trabajos/oportunidades en Upwork, Reddit o LinkedIn. También para research, copy, outreach y propuestas. Tiene un scraper real de Playwright y un sistema de Scoring para filtrar leads.
- orchestrator_consult_file_agent: leer/escribir archivos, listar carpetas, mover/copiar, buscar por nombre o contenido.
- orchestrator_consult_email_agent: Gmail en SOLO LECTURA (listar, buscar) con OAuth2. No puede enviar correos.
- orchestrator_consult_calendar_agent: Google Calendar (eventos próximos, crear, borrar, buscar) con OAuth2.
- orchestrator_consult_voice_agent: grabación por micrófono + transcripción Whisper local.
- orchestrator_consult_image_agent: generación de imágenes Stable Diffusion (diffusers, GPU CUDA recomendada).
- orchestrator_consult_computer_use_agent: PyAutoGUI + visión Ollama (llava): screenshot; clic/teclado/apps solo si el usuario lo habilitó.
- orchestrator_consult_github_agent: API GitHub (repos, archivos, issues, PRs) con GITHUB_TOKEN.
- orchestrator_consult_rag_agent: RAG LlamaIndex + Chroma sobre data/documents/.
- orchestrator_consult_obsidian_agent: leer, escribir y buscar notas en el vault local de Obsidian del usuario.
- orchestrator_consult_brain_agent: tu SEGUNDO CEREBRO. Analiza notas recientes de Obsidian y genera insights/newsletters.
- orchestrator_consult_morning_briefing_agent: USAR para generar un reporte diario ("Morning Briefing") consolidado con tareas, clima, calendario, correos y noticias.
- orchestrator_consult_skillforge_agent: crear y guardar una herramienta (skill) nueva y permanente.
- orchestrator_consult_mcp_agent: git/GitHub (commits, ramas, diffs, PRs). Push y merge requieren aprobación humana.
- rag_query_obsidian: consulta DIRECTA a la base de conocimiento de Obsidian (notas del proyecto, agentes, documentacion personal). Usala ANTES de delegar si el usuario pregunta sobre el proyecto, como funciona algo, o pide contexto.
- rag_index_obsidian_vault: indexa el vault de Obsidian en Chroma (ejecutar una vez o cuando haya notas nuevas).

Herramientas MCP (Model Context Protocol): si aparecen en tu lista, provienen de servidores MCP externos
conectados por configuracion (suelen llevar prefijo del nombre del servidor, p.ej. demo_echo).
Usalas cuando el usuario pida capacidades que esas tools declaren en su descripcion.

Reglas:
- MEMORIA DE CONVERSACIÓN: Tienes acceso al historial COMPLETO de esta sesión en tu contexto (todos los mensajes anteriores están en tu ventana de contexto). Si el usuario pregunta "¿qué te pregunté antes?", "¿qué dijiste?", "resume la conversación", "recuérdame X" — LEE TU PROPIO HISTORIAL DE MENSAJES y responde directamente. NUNCA uses herramientas para responder sobre la conversación actual.
- Para saludos o preguntas triviales que no requieran datos externos ni ejecucion, responde directamente SIN herramientas.
- Si el usuario pregunta sobre el proyecto AI-Forge, los agentes, herramientas o documentacion, usa PRIMERO rag_query_obsidian para obtener contexto relevante de las notas.
- Si delegas, sintetiza al final la respuesta util; no dejes solo salidas crudas sin contexto.
- Una peticion puede requerir varias herramientas en secuencia si es necesario.
- REGLA CRÍTICA DE ROUTING: Si el usuario pide buscar "clientes", "leads", "trabajos", "oportunidades", "scraping de Upwork", "scraping de Reddit" o cualquier variación → usa SIEMPRE orchestrator_consult_marketing_agent. NUNCA uses orchestrator_consult_web_search_agent para leads de trabajo."""


def get_orchestrator_graph():
    global _ORCHESTRATOR
    if _ORCHESTRATOR is None:
        base_tools = build_orchestrator_tools()
        router = get_model_router()
        try:
            llm, reason = router.get_model(prompt_token_count=0)
            if reason:
                a2a_log("orchestrator", "model_router", "fallback", reason.value)
        except RuntimeError:
            # Cloud no disponible o deshabilitado — usar local directamente
            llm = get_llm(temperature=0.12)

        _ORCHESTRATOR = create_react_agent(
            llm,
            tools=base_tools,
            prompt=ORCH_PROMPT,
            name="orchestrator_agent",
            checkpointer=_CHECKPOINTER,
        )
    return _ORCHESTRATOR


def _run_memory_gate(user_text: str, response_text: str) -> None:
    """Evalúa el turno completo con MemoryGate en background (no bloquea la respuesta)."""
    try:
        from agents.memory.memory_gate import MemoryGate
        from agents.chroma_memory import _get_collection
        llm = get_llm(temperature=0.0)
        collection = _get_collection()
        gate = MemoryGate(llm, collection)
        content = f"Usuario: {user_text}\nAsistente: {response_text}"
        gate.evaluate_and_store(content=content, context=user_text[:300])
    except Exception as e:  # hilo en background: registrar y seguir
        log.exception("MemoryGate failed")
        a2a_log("orchestrator", "memory_gate", "error", str(e))


def run_turn(user_text: str, thread_id: str = "default") -> AIMessage:
    """Un turno de conversación con memoria de hilo (thread_id identifica la sesión)."""
    trace = uuid.uuid4().hex[:8]
    set_trace_id(trace)

    a2a_log("cli", "orchestrator", "user_message", user_text)
    app = get_orchestrator_graph()
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 25}
    try:
        final = app.invoke(
            {"messages": [HumanMessage(content=user_text.strip())]},
            config=config,
        )
        text = extract_final_ai_text(final)
        body = text or "(sin respuesta)"
    except GraphRecursionError:
        a2a_log("orchestrator", "cli", "error", "Límite de recursión alcanzado (loops infinitos evitados).")
        body = "Error: Alcanzé el límite máximo de pasos de pensamiento para esta solicitud. Por favor, sé más específico o simplifica tu petición."

    # MemoryGate: evaluar el turno en background sin bloquear la respuesta al usuario
    threading.Thread(
        target=_run_memory_gate,
        args=(user_text, body),
        daemon=True
    ).start()

    return AIMessage(content=body)



def _text_parts(content) -> list[str]:
    """Extrae los fragmentos de texto de un chunk (str o lista de bloques)."""
    if not content:
        return []
    if isinstance(content, str):
        return [content]
    parts = []
    for block in content if isinstance(content, list) else []:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block["text"])
    return parts


async def arun_turn_stream(user_text: str, thread_id: str = "default") -> AsyncGenerator[str, None]:
    """Versión streaming async del orquestador. Emite chunks de texto conforme el LLM los genera."""
    trace = uuid.uuid4().hex[:8]
    set_trace_id(trace)

    a2a_log("dashboard", "orchestrator", "stream_message", user_text)
    app = get_orchestrator_graph()
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 25}
    full_response: list[str] = []
    try:
        async for chunk in app.astream(
            {"messages": [HumanMessage(content=user_text.strip())]},
            config=config,
            stream_mode="messages",
        ):
            msg, _metadata = chunk
            for text in _text_parts(getattr(msg, "content", None)):
                full_response.append(text)
                yield text
    except GraphRecursionError:
        a2a_log("orchestrator", "dashboard", "error", "Límite de recursión alcanzado.")
        yield "\n\nError: Alcanzé el límite máximo de pasos de pensamiento. Intenta de nuevo."

    # MemoryGate: evaluar el turno completo en background después del stream
    if full_response:
        threading.Thread(
            target=_run_memory_gate,
            args=(user_text, "".join(full_response)),
            daemon=True
        ).start()
