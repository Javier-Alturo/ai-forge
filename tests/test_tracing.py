"""Tracing: off by default, local-only, and the sub-agent trace nests under the orchestrator."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from langchain_core.callbacks import BaseCallbackHandler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import subagent_runner  # noqa: E402
from agents.registry import AgentConfig  # noqa: E402
from observability import tracing  # noqa: E402


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    for var in ("LANGFUSE_ENABLED", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST", "LANGFUSE_ALLOW_REMOTE"):
        monkeypatch.delenv(var, raising=False)
    tracing.get_handler.cache_clear()
    yield
    tracing.get_handler.cache_clear()


def _enable(monkeypatch, host="http://localhost:3000"):
    monkeypatch.setenv("LANGFUSE_ENABLED", "1")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "test-secret")
    monkeypatch.setenv("LANGFUSE_HOST", host)


@pytest.mark.parametrize(("url", "local"), [
    ("http://localhost:3000", True), ("http://127.0.0.1:3000", True), ("http://langfuse.localhost", True),
    ("https://cloud.langfuse.com", False), ("http://192.168.1.20:3000", False),
])
def test_is_local_host(url, local):
    assert tracing.is_local_host(url) is local


def test_disabled_by_default():
    assert tracing.callbacks() == []
    assert tracing.with_tracing({"a": 1}, name="x") == {"a": 1}


def test_remote_host_refused(monkeypatch):
    _enable(monkeypatch, host="https://cloud.langfuse.com")
    assert tracing.get_handler() is None


def test_enabled_adds_handler_and_metadata(monkeypatch):
    pytest.importorskip("langfuse")
    _enable(monkeypatch)
    cfg = tracing.with_tracing({"configurable": {"thread_id": "t1"}}, name="turn", session_id="t1", tags=["orch"])
    assert len(cfg["callbacks"]) == 1 and cfg["run_name"] == "turn"
    assert cfg["metadata"] == {"langfuse_session_id": "t1", "langfuse_tags": ["orch"]}
    assert cfg["configurable"] == {"thread_id": "t1"}


def test_child_config_inherits_callbacks():
    parent = {"callbacks": ["cb"], "metadata": {"langfuse_session_id": "s"}, "tags": ["orchestrator"]}
    child = subagent_runner.child_config("fitness", parent)
    assert child["callbacks"] == ["cb"] and child["run_name"] == "subagent:fitness"
    assert child["metadata"] == {"langfuse_session_id": "s"} and "agent:fitness" in child["tags"]
    assert subagent_runner.child_config("x", None) is None


def test_subagent_run_nests_under_tool_run(monkeypatch):
    """End to end through the real consult tool: the sub-agent (other thread) gets a child callback manager."""
    from agents import orchestrator_tools

    monkeypatch.setattr(subagent_runner, "get_agent_config", lambda n: AgentConfig(n, True, 5, 10))
    seen = {}

    class LegacyAgent:
        def invoke(self, payload, config=None):
            seen["config"] = config
            from langchain_core.messages import AIMessage
            return {"messages": [AIMessage(content="ok")]}

    monkeypatch.setattr(orchestrator_tools, "_lazy_getter", lambda target: LegacyAgent)
    tool = orchestrator_tools._make_consult_tool("file", "unused:unused", "desc")

    class Recorder(BaseCallbackHandler):
        pass

    assert tool.invoke({"task": "lista archivos"}, config={"callbacks": [Recorder()]}) == "ok"
    cfg = seen["config"]
    assert cfg["recursion_limit"] == 35 and cfg["run_name"] == "subagent:file"
    assert getattr(cfg["callbacks"], "parent_run_id", None) is not None  # nested, not a new trace
