"""
Tests de integración del ModelRouter con AgentBase y Circuit Breaker.

Ejecutar con:
    python -m pytest tests/test_model_router_integration.py -v --tb=short
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
import pytest
from unittest.mock import MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# GRUPO 1: Tests del Circuit Breaker aislado
# ─────────────────────────────────────────────────────────────────────────────

class TestCircuitBreaker:
    """Tests del ModelRouter y su Circuit Breaker sin dependencias de LLM real."""

    @pytest.fixture
    def router(self):
        from core.model_router import ModelRouter
        return ModelRouter({
            "local_model": "qwen2.5:14b",
            "timeout_seconds": 30,
            "max_local_context": 8192,
            "allow_cloud_fallback": False,
        })

    def test_circuit_starts_closed(self, router):
        """El circuit breaker empieza cerrado — estado normal."""
        assert router.cb.is_open is False
        assert router.cb.failures == 0

    def test_three_failures_open_circuit(self, router):
        """3 fallos consecutivos abren el circuit breaker."""
        from core.model_router import FallbackReason
        for _ in range(3):
            router.report_failure(FallbackReason.INFERENCE_ERROR)
        assert router.cb.is_open is True
        assert router.cb.failures == 3

    def test_two_failures_keep_circuit_closed(self, router):
        """2 fallos NO deben abrir el circuit (umbral = 3)."""
        from core.model_router import FallbackReason
        router.report_failure(FallbackReason.INFERENCE_ERROR)
        router.report_failure(FallbackReason.INFERENCE_ERROR)
        assert router.cb.is_open is False

    def test_success_resets_circuit(self, router):
        """Un éxito después de 2 fallos resetea el contador."""
        from core.model_router import FallbackReason
        router.report_failure(FallbackReason.INFERENCE_ERROR)
        router.report_failure(FallbackReason.INFERENCE_ERROR)
        router.report_success()
        assert router.cb.failures == 0
        assert router.cb.is_open is False

    def test_context_overflow_triggers_fallback(self, router):
        """Prompt demasiado largo (> max_local_context) debe pedir fallback."""
        from core.model_router import FallbackReason
        with pytest.raises(RuntimeError, match="cloud_fallback"):
            router.get_model(prompt_token_count=99999)

    def test_cloud_disabled_raises_when_circuit_open(self, router):
        """Sin cloud habilitado, circuit abierto debe lanzar RuntimeError."""
        from core.model_router import FallbackReason
        for _ in range(3):
            router.report_failure(FallbackReason.INFERENCE_ERROR)

        with pytest.raises(RuntimeError, match="cloud_fallback"):
            router.get_model(100)

    def test_circuit_recovery_after_timeout(self, router):
        """El circuit se cierra automáticamente después del recovery timeout."""
        from core.model_router import FallbackReason
        router.cb.RECOVERY_TIMEOUT = 0.05  # 50ms para el test

        for _ in range(3):
            router.report_failure(FallbackReason.INFERENCE_ERROR)
        assert router.cb.is_open is True

        time.sleep(0.1)

        # _should_use_cloud() verifica el tiempo — simulamos llamada a get_model
        # Con cloud deshabilitado, si el circuit se cierra, debe intentar local
        # y no lanzar RuntimeError de cloud
        with patch.object(router, "_get_local_model", return_value=MagicMock()):
            model, reason = router.get_model(100)
        assert router.cb.is_open is False

    def test_get_status_returns_dict(self, router):
        """get_status() debe retornar dict con todos los campos esperados."""
        status = router.get_status()
        assert "local_model" in status
        assert "circuit_breaker_open" in status
        assert "consecutive_failures" in status
        assert "failure_threshold" in status
        assert isinstance(status["circuit_breaker_open"], bool)

    def test_from_config_reads_agents_config_json(self):
        """from_config() debe leer la sección model_router del config."""
        from core.model_router import ModelRouter
        full_cfg = {
            "model_router": {
                "local_model": "llama3:8b",
                "allow_cloud_fallback": False,
                "cb_failure_threshold": 5,
            }
        }
        router = ModelRouter.from_config(full_cfg)
        assert router.local_model_name == "llama3:8b"
        assert router.cb.FAILURE_THRESHOLD == 5


# ─────────────────────────────────────────────────────────────────────────────
# GRUPO 2: Tests de AgentBase con ModelRouter inyectado
# ─────────────────────────────────────────────────────────────────────────────

class TestAgentBaseWithRouter:
    """Tests de AgentBase con ModelRouter mockeado — sin llamadas a Ollama."""

    @pytest.fixture
    def mock_router(self):
        router = MagicMock()
        router.get_model.return_value = (MagicMock(), None)
        return router

    @pytest.fixture
    def success_agent(self, mock_router):
        """Agente concreto mínimo que siempre tiene éxito."""
        from agents.agent_base import AgentBase

        class OkAgent(AgentBase):
            @property
            def name(self):
                return "ok_agent"

            def _run(self, user_input, context, config):
                return f"resultado para: {user_input}"

        return OkAgent(config={}, model_router=mock_router)

    @pytest.fixture
    def failing_agent(self, mock_router):
        """Agente concreto mínimo que siempre falla."""
        from agents.agent_base import AgentBase

        class FailAgent(AgentBase):
            @property
            def name(self):
                return "fail_agent"

            def _run(self, user_input, context, config):
                raise ConnectionError("Ollama no disponible")

        return FailAgent(config={}, model_router=mock_router)

    def test_success_calls_report_success(self, success_agent, mock_router):
        """Ejecución exitosa debe llamar report_success() en el router."""
        result = success_agent.invoke({"input": "haz algo"})
        mock_router.report_success.assert_called_once()
        assert result.status == "ok"

    def test_failure_calls_report_failure(self, failing_agent, mock_router):
        """Excepción en _run() debe llamar report_failure() en el router."""
        result = failing_agent.invoke({"input": "haz algo"})
        mock_router.report_failure.assert_called_once()
        assert result.status == "error"

    def test_failure_returns_structured_dict(self, failing_agent, mock_router):
        """El error debe ser AgentResult estructurado, NUNCA una excepción cruda."""
        result = failing_agent.invoke({"input": "haz algo"})

        assert result.status == "error"
        assert "Ollama no disponible" in result.error
        assert result.trace_id is not None
        assert result.duration_ms >= 0
        assert result.data == ""

    def test_success_returns_structured_result(self, success_agent, mock_router):
        """Resultado exitoso debe ser AgentResult completo."""
        result = success_agent.invoke({"input": "test"})

        assert result.status == "ok"
        assert "test" in result.data
        assert result.error is None
        assert result.trace_id is not None
        assert result.duration_ms >= 0

    def test_agent_without_router_works(self):
        """AgentBase sin router inyectado debe funcionar normalmente (legacy)."""
        from agents.agent_base import AgentBase

        class SimpleAgent(AgentBase):
            @property
            def name(self):
                return "simple"

            def _run(self, user_input, context, config):
                return "ok sin router"

        agent = SimpleAgent(config={}, model_router=None)
        result = agent.invoke({"input": "test legacy"})
        assert result.status == "ok"
        assert result.error is None

    def test_get_llm_with_router(self, success_agent, mock_router):
        """get_llm() con router debe llamar get_model() del router."""
        mock_router.get_model.return_value = (MagicMock(), None)
        llm = success_agent.get_llm("mi prompt de prueba")
        mock_router.get_model.assert_called_once()

    def test_get_llm_without_router(self):
        """get_llm() sin router debe usar get_llm() de agents.llm."""
        from agents.agent_base import AgentBase

        class NoRouterAgent(AgentBase):
            @property
            def name(self):
                return "no_router"
            def _run(self, u, c, cfg):
                return ""

        agent = NoRouterAgent(config={})
        with patch("agents.llm.get_llm", return_value=MagicMock()) as mock_get_llm:
            llm = agent.get_llm("test")
            mock_get_llm.assert_called_once()

    def test_estimate_tokens_basic(self, success_agent):
        """_estimate_tokens() debe retornar ~len/4."""
        text = "a" * 400
        assert success_agent._estimate_tokens(text) == 100

    def test_invoke_with_messages_payload(self, success_agent, mock_router):
        """Compatibilidad con payload tipo LangGraph (messages=[HumanMessage()])."""
        from langchain_core.messages import HumanMessage

        result = success_agent.invoke({
            "messages": [HumanMessage(content="mensaje de langraph")]
        })
        assert result.status == "ok"
        assert "mensaje de langraph" in result.data


# ─────────────────────────────────────────────────────────────────────────────
# GRUPO 3: Tests de integración router ↔ orquestador
# ─────────────────────────────────────────────────────────────────────────────

class TestRouterInjectionInOrchestrator:
    """Verificar que el orquestador inyecta el router en sub-agentes AgentBase."""

    def test_agentbase_receives_router_attribute(self):
        """Un AgentBase instanciado debe aceptar model_router en __init__."""
        from agents.agent_base import AgentBase
        from core.model_router import ModelRouter

        class DummyAgent(AgentBase):
            @property
            def name(self): return "dummy"
            def _run(self, u, c, cfg): return ""

        router = ModelRouter({"local_model": "qwen2.5:14b", "allow_cloud_fallback": False})
        agent = DummyAgent(config={}, model_router=router)
        assert agent.router is router

    def test_agentbase_router_defaults_to_none(self):
        """Sin router explícito, agent.router debe ser None."""
        from agents.agent_base import AgentBase

        class DummyAgent(AgentBase):
            @property
            def name(self): return "dummy"
            def _run(self, u, c, cfg): return ""

        agent = DummyAgent(config={})
        assert agent.router is None
