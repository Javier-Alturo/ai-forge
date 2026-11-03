"""Orquestador principal: grafo LangGraph ReAct que invoca otros agentes como tools (A2A)."""

from __future__ import annotations

import threading
import uuid
from typing import Any, AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.prebuilt import create_react_agent
from ollama import ResponseError

from agents.a2a_log import a2a_log
from agents.llm import OLLAMA_BASE, OLLAMA_MODEL, get_llm
from agents.logger import get_logger, set_trace_id
from agents.message_utils import extract_final_ai_text
from agents.orchestrator_tools import build_orchestrator_tools
from agents.subagent_runner import get_model_router, invoke_subagent
from core.tool_call_repair import repair_message
from observability.tracing import with_tracing

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

# Same value the evals use. At Ollama's default it skips tools far more often (routing 91% vs 83-85%).
ORCHESTRATOR_TEMPERATURE = 0.0

MODEL_ERROR_MESSAGE = "El modelo local falló al generar la respuesta (por ejemplo, Ollama la cortó por repetición). Intenta de nuevo o reformula tu petición."

# Short on purpose: tools describe themselves in their schemas. Repeating that list here made
# qwen2.5:14b garble tool calls and hit Ollama's repeat limit (evals: 12 errors in 188 runs vs 0).
ORCH_PROMPT = """Eres el ORQUESTADOR principal del sistema multi-agente (A2A con LangGraph).
Responde al usuario en español.

Usa la herramienta adecuada para responder.
Si el usuario pregunta por lo dicho en esta conversación ("¿qué te pregunté antes?", "resume la conversación"), responde con tu historial de mensajes, SIN herramientas.
Para saludos o preguntas triviales, responde directamente sin herramientas.
Si delegas, sintetiza la respuesta final."""


def get_orchestrator_graph():
    global _ORCHESTRATOR
    if _ORCHESTRATOR is None:
        base_tools = build_orchestrator_tools()
        router = get_model_router()
        try:
            llm, reason = router.get_model(prompt_token_count=0, temperature=ORCHESTRATOR_TEMPERATURE)
            if reason:
                a2a_log("orchestrator", "model_router", "fallback", reason.value)
        except RuntimeError:
            # Cloud no disponible o deshabilitado — usar local directamente
            llm = get_llm(temperature=ORCHESTRATOR_TEMPERATURE)

        _ORCHESTRATOR = create_react_agent(
            llm,
            tools=base_tools,
            prompt=ORCH_PROMPT,
            name="orchestrator_agent",
            checkpointer=_CHECKPOINTER,
            post_model_hook=make_repair_hook([tool.name for tool in base_tools]),
        )
    return _ORCHESTRATOR


def make_repair_hook(tool_names: list[str]):
    """Graph node run after each LLM turn: a tool call written as text becomes a real one."""

    def repair_tool_calls(state: dict[str, Any]) -> dict[str, Any]:
        last = state["messages"][-1]
        fixed = repair_message(last, tool_names) if isinstance(last, AIMessage) else last
        return {"messages": [fixed] if fixed is not last else []}

    return repair_tool_calls


_BACKGROUND: list[threading.Thread] = []


def _start_background(target, *args) -> None:
    """Run post-turn work (MemoryGate) without blocking the reply; tracked so CLIs can wait."""
    _BACKGROUND[:] = [t for t in _BACKGROUND if t.is_alive()]
    thread = threading.Thread(target=target, args=args, daemon=True)
    _BACKGROUND.append(thread)
    thread.start()


def wait_for_background_tasks(timeout: float = 60.0) -> None:
    """Call before a short-lived process exits; otherwise the interpreter shuts down mid-task
    and the turn's memory is never stored."""
    for thread in list(_BACKGROUND):
        thread.join(timeout)


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
    config = with_tracing(
        {"configurable": {"thread_id": thread_id}, "recursion_limit": 25},
        name="orchestrator_turn", session_id=thread_id, tags=["orchestrator"],
    )
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
    except ResponseError as e:
        log.warning("Ollama aborted the turn: %s", e)
        a2a_log("orchestrator", "cli", "error", str(e))
        body = MODEL_ERROR_MESSAGE

    # MemoryGate: evaluar el turno en background sin bloquear la respuesta al usuario
    _start_background(_run_memory_gate, user_text, body)

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
    config = with_tracing(
        {"configurable": {"thread_id": thread_id}, "recursion_limit": 25},
        name="orchestrator_turn", session_id=thread_id, tags=["orchestrator"],
    )
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
    except ResponseError as e:
        log.warning("Ollama aborted the turn: %s", e)
        a2a_log("orchestrator", "dashboard", "error", str(e))
        yield f"\n\n{MODEL_ERROR_MESSAGE}"

    # MemoryGate: evaluar el turno completo en background después del stream
    if full_response:
        _start_background(_run_memory_gate, user_text, "".join(full_response))
