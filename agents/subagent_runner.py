"""Run a sub-agent for the orchestrator with soft/hard timeouts and one retry.

Each attempt runs in its own thread and the executor is shut down with
wait=False, so a hung agent never blocks the orchestrator past `hard_s`.
"""

from __future__ import annotations

import concurrent.futures
import json
import time
from pathlib import Path
from typing import Any, Callable

from langchain_core.messages import HumanMessage

from agents.a2a_log import a2a_log
from agents.agent_base import AgentBase
from agents.llm import OLLAMA_MODEL
from agents.logger import get_logger
from agents.message_utils import extract_final_ai_text
from agents.registry import get_agent_config
from core.model_router import ModelRouter

log = get_logger("orchestrator")

MAX_ATTEMPTS = 2
_CONFIG_FILE = Path(__file__).resolve().parent.parent / "agents_config.json"
_MODEL_ROUTER: ModelRouter | None = None


class SubagentError(RuntimeError):
    """A sub-agent finished with status="error"."""


def get_model_router() -> ModelRouter:
    """Singleton del ModelRouter, configurado desde agents_config.json."""
    global _MODEL_ROUTER
    if _MODEL_ROUTER is None:
        try:
            full_cfg = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            _MODEL_ROUTER = ModelRouter.from_config(full_cfg)
            a2a_log("orchestrator", "model_router", "init",
                    f"local={_MODEL_ROUTER.local_model_name} cloud_fallback={_MODEL_ROUTER.allow_cloud}")
        except (OSError, ValueError) as e:
            a2a_log("orchestrator", "model_router", "init_error", str(e))
            _MODEL_ROUTER = ModelRouter({"local_model": OLLAMA_MODEL})
    return _MODEL_ROUTER


def _inject_router(agent: Any, name: str) -> None:
    """Fase 4: los agentes AgentBase usan el ModelRouter (circuit breaker)."""
    if isinstance(agent, AgentBase) and getattr(agent, "router", None) is None:
        agent.router = get_model_router()
        a2a_log("orchestrator", name, "router_injected", f"router→{name}")


def _call_agent(agent: Any, task: str) -> Any:
    if isinstance(agent, AgentBase):  # Fase 3: interfaz estandarizada
        res = agent.invoke({"input": task})
        if res.status == "error":
            raise SubagentError(res.error)
        return res.data
    # Legacy: grafo create_react_agent que devuelve un dict de mensajes
    return agent.invoke({"messages": [HumanMessage(content=task)]}, config={"recursion_limit": 35})


def _attempt(fn: Callable[[], Any], name: str, soft_s: float, hard_s: float) -> tuple[str, Any]:
    """Una ejecución con timeouts. Devuelve ("ok", resultado) | ("timeout", None) | ("error", exc)."""
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"agent-{name}")
    future = executor.submit(fn)
    try:
        try:
            return "ok", future.result(timeout=soft_s)
        except concurrent.futures.TimeoutError:
            a2a_log(name, "orchestrator", "timeout_soft", f"Tardando más de {soft_s}s, esperando...")
            return "ok", future.result(timeout=max(1, hard_s - soft_s))
    except concurrent.futures.TimeoutError:
        return "timeout", None
    except Exception as e:  # frontera: cualquier fallo del subagente se reporta al LLM
        log.exception("Subagent %s failed", name)
        return "error", e
    finally:
        executor.shutdown(wait=False, cancel_futures=True)  # nunca esperar a un hilo colgado


def invoke_subagent(name: str, getter: Callable[[], Any], task: str) -> str:
    cfg = get_agent_config(name)
    if not cfg.enabled:
        return f"Error: El agente {name} está deshabilitado por configuración."

    start_time = time.time()
    a2a_log("orchestrator", name, "invoke_subgraph", task)
    agent = getter()
    _inject_router(agent, name)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        status, value = _attempt(lambda: _call_agent(agent, task), name, cfg.soft_s, cfg.hard_s)
        if status == "ok":
            break
        last = attempt == MAX_ATTEMPTS
        if status == "timeout":
            if last:
                a2a_log(name, "orchestrator", "timeout_hard", f"Cancelado tras {cfg.hard_s}s")
                return f"Error: El agente {name} superó el tiempo máximo de {cfg.hard_s}s y fue cancelado."
            a2a_log(name, "orchestrator", "timeout_hard_retry", f"Intento {attempt} superó {cfg.hard_s}s. Reintentando...")
        else:
            if last:
                a2a_log(name, "orchestrator", "subgraph_error", str(value))
                return f"Error en agente {name}: {value}"
            a2a_log(name, "orchestrator", "subgraph_error_retry", f"Intento {attempt} falló: {value}. Reintentando...")

    text = str(value) if isinstance(agent, AgentBase) else extract_final_ai_text(value)
    duration_ms = int((time.time() - start_time) * 1000)
    a2a_log(name, "orchestrator", "subgraph_done", f"[{duration_ms}ms] " + (text[:200] if text else "(vacío)"))
    return text or "(El subagente no devolvió texto.)"
