"""
ModelRouter con Circuit Breaker — Protocolo de Fallback (Local → Cloud).

REGLA: Siempre local primero. Cloud solo si:
  1. El circuit breaker está abierto (demasiados fallos consecutivos del modelo local), o
  2. El prompt es demasiado largo para el contexto local.

El cloud fallback está DESHABILITADO por defecto (allow_cloud_fallback=False).
Para habilitarlo, configurar en agents_config.json.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class FallbackReason(Enum):
    TIMEOUT = "timeout"
    CONTEXT_OVERFLOW = "context_overflow"
    INFERENCE_ERROR = "inference_error"
    LOW_CONFIDENCE = "low_confidence"
    CIRCUIT_BREAKER = "circuit_breaker"


@dataclass
class CircuitBreakerState:
    failures: int = 0
    last_failure_time: float = 0.0
    is_open: bool = False   # True = local está caído, enrutar a cloud
    FAILURE_THRESHOLD: int = 3
    RECOVERY_TIMEOUT: float = 60.0  # segundos antes de reintentar local


class ModelRouter:
    """
    Decide qué modelo LLM usar en cada llamada con lógica de Circuit Breaker.

    Uso:
        router = ModelRouter.from_config(agents_config)
        model, reason = router.get_model(prompt_token_count=1500)
        if reason:
            logger.warning(f"Usando fallback. Razón: {reason.value}")
        response = model.invoke(prompt)
        router.report_success()
    """

    def __init__(self, config: dict):
        self.local_model_name: str = config.get("local_model", "qwen2.5:14b")
        self.cloud_model_name: Optional[str] = config.get("cloud_model")
        self.local_timeout: int = config.get("timeout_seconds", 45)
        self.max_local_tokens: int = config.get("max_local_context", 8192)
        self.allow_cloud: bool = config.get("allow_cloud_fallback", False)
        self.cb = CircuitBreakerState(
            FAILURE_THRESHOLD=config.get("cb_failure_threshold", 3),
            RECOVERY_TIMEOUT=config.get("cb_recovery_timeout_seconds", 60.0),
        )

    @classmethod
    def from_config(cls, full_config: dict) -> "ModelRouter":
        """Factory que lee la sección model_router de agents_config.json."""
        router_cfg = full_config.get("model_router", {})
        return cls(router_cfg)

    def get_model(self, prompt_token_count: int = 0) -> Tuple[object, Optional[FallbackReason]]:
        """
        Retorna (modelo, razón_de_fallback).
        razón_de_fallback es None si se usa local sin problemas.
        """
        if self._should_use_cloud(prompt_token_count):
            reason = (
                FallbackReason.CIRCUIT_BREAKER
                if self.cb.is_open
                else FallbackReason.CONTEXT_OVERFLOW
            )
            if not self.allow_cloud:
                raise RuntimeError(
                    f"Modelo local no disponible y cloud_fallback está DESHABILITADO. "
                    f"Razón: {self._get_fallback_reason(prompt_token_count)}. "
                    f"Para habilitar: agents_config.json → model_router.allow_cloud_fallback: true"
                )
            if not self.cloud_model_name:
                raise RuntimeError(
                    "cloud_fallback habilitado pero cloud_model no configurado en agents_config.json."
                )
            return self._get_cloud_model(), reason

        return self._get_local_model(), None

    def report_failure(self, reason: FallbackReason = FallbackReason.INFERENCE_ERROR) -> None:
        """Llamar desde el agente cuando el modelo falla."""
        self.cb.failures += 1
        self.cb.last_failure_time = time.time()
        if self.cb.failures >= self.cb.FAILURE_THRESHOLD:
            self.cb.is_open = True

    def report_success(self) -> None:
        """Llamar desde el agente después de cada respuesta exitosa."""
        self.cb.failures = 0
        self.cb.is_open = False

    def get_status(self) -> dict:
        """Retorna el estado actual del router para el dashboard."""
        return {
            "local_model": self.local_model_name,
            "cloud_model": self.cloud_model_name,
            "allow_cloud_fallback": self.allow_cloud,
            "circuit_breaker_open": self.cb.is_open,
            "consecutive_failures": self.cb.failures,
            "failure_threshold": self.cb.FAILURE_THRESHOLD,
            "recovery_timeout_seconds": self.cb.RECOVERY_TIMEOUT,
        }

    # ── Internals ──────────────────────────────────────────────────────────────

    def _should_use_cloud(self, token_count: int) -> bool:
        if self.cb.is_open:
            # Intentar recuperación si pasó suficiente tiempo
            elapsed = time.time() - self.cb.last_failure_time
            if elapsed > self.cb.RECOVERY_TIMEOUT:
                self.cb.is_open = False
                return False
            return True
        return token_count > self.max_local_tokens

    def _get_fallback_reason(self, token_count: int) -> str:
        if self.cb.is_open:
            return f"Circuit breaker abierto ({self.cb.failures} fallos consecutivos)"
        if token_count > self.max_local_tokens:
            return f"Contexto {token_count} > máximo local {self.max_local_tokens}"
        return "desconocida"

    def _get_local_model(self):
        import os
        from langchain_ollama import ChatOllama
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        return ChatOllama(
            model=self.local_model_name,
            base_url=base_url,
            timeout=self.local_timeout,
        )

    def _get_cloud_model(self):
        try:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(model=self.cloud_model_name)  # type: ignore[arg-type]
        except ImportError:
            raise RuntimeError(
                "langchain_anthropic no está instalado. "
                "Ejecuta: pip install langchain-anthropic"
            )
