"""Sub-agent runner: hard timeouts return on time, retries, error reporting."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import subagent_runner as runner  # noqa: E402
from agents.registry import AgentConfig  # noqa: E402


@pytest.fixture
def cfg(monkeypatch):
    def set_cfg(soft=0.2, hard=0.5, enabled=True):
        monkeypatch.setattr(runner, "get_agent_config", lambda name: AgentConfig(name, enabled, soft, hard))
    set_cfg()
    return set_cfg


class FakeAgent:
    """Legacy-style agent: invoke() returns a LangGraph-like dict."""

    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls = 0

    def invoke(self, payload, config=None):
        self.calls += 1
        return self.behaviour(self.calls)


def _reply(text):
    from langchain_core.messages import AIMessage

    return {"messages": [AIMessage(content=text)]}


def test_success(cfg):
    agent = FakeAgent(lambda n: _reply("hola"))
    assert runner.invoke_subagent("x", lambda: agent, "task") == "hola"


def test_disabled_agent(cfg):
    cfg(enabled=False)
    assert "deshabilitado" in runner.invoke_subagent("x", lambda: FakeAgent(None), "t")


def test_hung_agent_returns_after_hard_timeout(cfg):
    release = threading.Event()
    agent = FakeAgent(lambda n: release.wait(30) and _reply("tarde"))
    start = time.monotonic()
    out = runner.invoke_subagent("slow", lambda: agent, "task")
    elapsed = time.monotonic() - start
    release.set()
    assert "superó el tiempo máximo" in out
    # 2 attempts x 0.5s hard timeout; before the fix this blocked until the agent finished (30s).
    assert elapsed < 5


def test_retry_after_error_then_success(cfg):
    def behaviour(n):
        if n == 1:
            raise ValueError("boom")
        return _reply("ok en 2do intento")

    agent = FakeAgent(behaviour)
    assert runner.invoke_subagent("x", lambda: agent, "task") == "ok en 2do intento"
    assert agent.calls == 2


def test_error_after_all_attempts(cfg):
    agent = FakeAgent(lambda n: (_ for _ in ()).throw(RuntimeError("caído")))
    out = runner.invoke_subagent("x", lambda: agent, "task")
    assert out.startswith("Error en agente x") and "caído" in out
    assert agent.calls == runner.MAX_ATTEMPTS
