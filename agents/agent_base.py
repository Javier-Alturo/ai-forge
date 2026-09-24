"""Clase base para la Fase 3: Desacoplamiento de Agentes.

Estandariza la interfaz de invoke() para que todos reciban:
{ "input": str, "context": dict }

Y retornen un AgentResult:
{ "status": "ok|error|warn", "data": str, "error": str | None, "trace_id": str, "duration_ms": int }

Fase 4: ModelRouter inyectado opcionalmente.
Cuando el router está presente, invoke() reporta éxito/fallo al Circuit Breaker
y get_llm() retorna el modelo correcto según el estado del router.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from pydantic import BaseModel

from agents.logger import get_trace_id

logger = logging.getLogger(__name__)


class AgentResult(BaseModel):
    status: str  # "ok", "error", "warn"
    data: str
    error: str | None = None
    trace_id: str
    duration_ms: int


class AgentBase(ABC):
    """Clase base que todos los agentes deberían heredar para estandarizar I/O.

    Fase 4: soporta inyección opcional de ModelRouter para Circuit Breaker.

    Uso con router:
        agent = MyAgent(config=cfg, model_router=router)
        result = agent.invoke({"input": "tarea"})
        # invoke() reporta éxito/fallo al circuit breaker automáticamente

    Uso sin router (legacy):
        agent = MyAgent(config=cfg)
        result = agent.invoke({"input": "tarea"})
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, model_router=None):
        """
        Args:
            config: Configuración del agente (dict libre).
            model_router: Instancia de ModelRouter. Si es None, usa LLM local por defecto.
        """
        self.config = config or {}
        self.router = model_router  # Inyectado desde el Orquestador

    @property
    @abstractmethod
    def name(self) -> str:
        """Nombre identificador del agente (ej. 'memory')."""
        pass

    def get_llm(self, prompt_text: str = ""):
        """
        Obtener el LLM correcto según el estado del ModelRouter.

        Si hay router inyectado → usa get_model() con estimación de tokens.
        Si no hay router → usa LLM local por defecto (comportamiento legacy).

        Uso en _run():
            llm = self.get_llm(user_input)
            response = llm.invoke(prompt)
        """
        router = getattr(self, "router", None)
        if router:
            token_estimate = self._estimate_tokens(prompt_text)
            try:
                model, reason = router.get_model(prompt_token_count=token_estimate)
                if reason:
                    logger.warning(f"[{self.name}] Fallback activo: {reason.value}")
                return model
            except RuntimeError as e:
                # Cloud deshabilitado o no configurado — degradar a local
                logger.warning(f"[{self.name}] Router error (usando local por defecto): {e}")

        from agents.llm import get_llm
        return get_llm()

    def _estimate_tokens(self, text: str) -> int:
        """Estimación rápida: ~4 chars por token."""
        return len(text) // 4

    def invoke(self, payload: Dict[str, Any], config: Dict[str, Any] | None = None) -> AgentResult:
        """
        Punto de entrada estandarizado.
        El payload espera al menos la clave "input".

        Fase 4: reporta éxito/fallo al ModelRouter Circuit Breaker.
        NUNCA sobreescribir este método.
        """
        start_t = time.time()
        trace_id = get_trace_id()

        user_input = payload.get("input", "")
        if not user_input and "messages" in payload:
            # Compatibilidad si se llama tipo LangGraph
            from langchain_core.messages import HumanMessage
            msgs = payload["messages"]
            if msgs and isinstance(msgs[-1], HumanMessage):
                user_input = str(msgs[-1].content)

        context = payload.get("context", {})

        logger.debug(f"[{self.name}][{trace_id}] invoke() → {user_input[:80]}...")

        try:
            result_data = self._run(user_input, context, config)
            status = "ok"
            error = None

            # Reportar éxito al circuit breaker
            router = getattr(self, "router", None)
            if router:
                router.report_success()
                logger.debug(f"[{self.name}][{trace_id}] report_success() → CB")

        except Exception as e:
            status = "error"
            result_data = ""
            error = str(e)

            # Reportar fallo al circuit breaker
            router = getattr(self, "router", None)
            if router:
                from core.model_router import FallbackReason
                router.report_failure(FallbackReason.INFERENCE_ERROR)
                logger.warning(f"[{self.name}][{trace_id}] report_failure() → CB | {e}")
            else:
                logger.error(f"[{self.name}][{trace_id}] Error (sin router): {e}")

        duration_ms = int((time.time() - start_t) * 1000)

        return AgentResult(
            status=status,
            data=result_data,
            error=error,
            trace_id=trace_id,
            duration_ms=duration_ms,
        )

    @abstractmethod
    def _run(self, user_input: str, context: Dict[str, Any], config: Dict[str, Any] | None) -> str:
        """Implementación real del agente. Debe retornar un string o lanzar excepción."""
        pass
