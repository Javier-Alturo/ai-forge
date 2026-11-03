"""Orchestrator tool table: names are unique and match the prompt."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_tool_table_names_are_unique_and_stable():
    from agents.orchestrator_tools import SUBAGENTS, tool_name

    names = [tool_name(agent) for agent, _, _ in SUBAGENTS]
    assert len(names) == len(set(names))
    assert "orchestrator_consult_mcp_agent" in names
    assert "orchestrator_consult_web_search_agent" in names


def test_subagent_tools_describe_themselves():
    """The prompt does not list the tools, so each schema must say what its tool is for."""
    from agents.orchestrator import ORCH_PROMPT
    from agents.orchestrator_tools import SUBAGENTS, tool_name

    assert all(description.strip() for _, _, description in SUBAGENTS)
    assert [tool_name(a) for a, _, _ in SUBAGENTS if tool_name(a) in ORCH_PROMPT] == []


def _aborting_graph(monkeypatch):
    from ollama import ResponseError

    from agents import orchestrator

    class Graph:
        def invoke(self, *_, **__):
            raise ResponseError("prediction aborted, token repeat limit reached")

        async def astream(self, *_, **__):
            raise ResponseError("prediction aborted, token repeat limit reached")
            yield  # makes this an async generator

    monkeypatch.setattr(orchestrator, "get_orchestrator_graph", Graph)
    monkeypatch.setattr(orchestrator, "_start_background", lambda *_: None)
    return orchestrator


def test_run_turn_survives_ollama_abort(monkeypatch):
    orchestrator = _aborting_graph(monkeypatch)
    assert orchestrator.run_turn("hola").content == orchestrator.MODEL_ERROR_MESSAGE


def test_stream_survives_ollama_abort(monkeypatch):
    import asyncio

    orchestrator = _aborting_graph(monkeypatch)

    async def collect():
        return [chunk async for chunk in orchestrator.arun_turn_stream("hola")]

    assert orchestrator.MODEL_ERROR_MESSAGE in "".join(asyncio.run(collect()))


def test_reminder_daemon_can_be_disabled(monkeypatch):
    import sys as _sys
    import types

    from agents import orchestrator_tools

    started = []
    fake = types.SimpleNamespace(start_reminder_daemon=lambda: started.append(True))
    monkeypatch.setitem(_sys.modules, "agents.reminder_agent", fake)
    monkeypatch.setenv("AIFORGE_DISABLE_REMINDERS", "1")
    orchestrator_tools._start_reminder_daemon()
    assert started == []
    monkeypatch.delenv("AIFORGE_DISABLE_REMINDERS")
    orchestrator_tools._start_reminder_daemon()
    assert started == [True]
