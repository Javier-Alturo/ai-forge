"""LangFuse tracing for LangChain/LangGraph runs — local-only by default.

Off unless LANGFUSE_ENABLED=1 and both keys are set. Traces are only sent to a host on
this machine (localhost / 127.0.0.1); a remote LANGFUSE_HOST is refused unless
LANGFUSE_ALLOW_REMOTE=1, so conversations never leave the PC by accident.

Usage:
    config = with_tracing({"configurable": {...}}, name="orchestrator_turn", session_id=thread_id)
    graph.invoke(inputs, config=config)
"""

from __future__ import annotations

import atexit
import logging
import os
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

log = logging.getLogger("ai_forge.tracing")

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def is_local_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in LOCAL_HOSTS or host.endswith(".localhost")


def tracing_enabled() -> bool:
    return (
        os.environ.get("LANGFUSE_ENABLED", "").strip() == "1"
        and bool(os.environ.get("LANGFUSE_PUBLIC_KEY"))
        and bool(os.environ.get("LANGFUSE_SECRET_KEY"))
    )


@lru_cache(maxsize=1)
def get_handler():
    """The LangFuse LangChain callback handler, or None if tracing is off/unavailable."""
    if not tracing_enabled():
        return None
    host = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
    if not is_local_host(host) and os.environ.get("LANGFUSE_ALLOW_REMOTE") != "1":
        log.error("LANGFUSE_HOST=%s no es local; tracing desactivado (usa LANGFUSE_ALLOW_REMOTE=1 si es intencional)", host)
        return None
    try:
        from langfuse.langchain import CallbackHandler
    except ImportError:
        log.warning("Paquete 'langfuse' no instalado; tracing desactivado", exc_info=True)
        return None
    handler = CallbackHandler()
    atexit.register(flush)
    return handler


def callbacks() -> list:
    handler = get_handler()
    return [handler] if handler else []


def with_tracing(
    config: dict[str, Any] | None,
    *,
    name: str,
    session_id: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Return a copy of a LangChain config with the tracer, a run name and LangFuse metadata."""
    config = dict(config or {})
    cbs = callbacks()
    if not cbs:
        return config
    config["callbacks"] = [*(config.get("callbacks") or []), *cbs]
    config["run_name"] = name
    metadata = dict(config.get("metadata") or {})
    if session_id:
        metadata["langfuse_session_id"] = session_id
    if tags:
        metadata["langfuse_tags"] = tags
    config["metadata"] = metadata
    return config


def flush() -> None:
    """Send buffered spans (call before a short-lived script exits)."""
    if get_handler() is None:
        return
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception:  # never let telemetry break the app on exit
        log.exception("LangFuse flush failed")
