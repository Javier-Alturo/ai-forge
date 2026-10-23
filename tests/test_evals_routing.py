"""Routing eval with a fake LLM (no Ollama needed)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals import datasets  # noqa: E402
from evals.suites import routing  # noqa: E402


class FakeMsg:
    def __init__(self, tool):
        self.tool_calls = [{"name": tool, "args": {"task": "x"}}] if tool else []


class FakeLLM:
    """Routes by keyword; records the tools it was bound with."""

    def __init__(self, rules):
        self.rules = rules
        self.bound_names = []

    def bind_tools(self, tools):
        self.bound_names = [t.name for t in tools]
        return self

    def invoke(self, messages):
        text = messages[-1].content.lower()
        return FakeMsg(next((tool for kw, tool in self.rules if kw in text), None))


def test_label_for_tool():
    assert routing.label_for_tool("orchestrator_consult_taskforge_agent") == "taskforge"
    assert routing.label_for_tool("orchestrator_consult_mcp_agent") == "mcp"
    assert routing.label_for_tool("find_real_leads") == "find_real_leads"


def test_score_accepts_alternatives():
    items = [
        {"text": "a", "expected": ["marketing", "find_real_leads"]},
        {"text": "b", "expected": ["file"]},
        {"text": "c", "expected": ["none"]},
    ]
    result = routing.score(items, ["find_real_leads", "email", "none"])
    assert result["accuracy"] == pytest.approx(0.667, abs=1e-3)
    assert result["confusion"]["file"]["email"] == 1
    assert [e["text"] for e in result["errors"]] == ["b"]


def test_run_with_fake_llm_uses_real_tool_names():
    llm = FakeLLM([("calendario", "orchestrator_consult_calendar_agent"), ("upwork", "find_real_leads")])
    items = [
        {"text": "¿Qué hay en mi calendario?", "expected": ["calendar"]},
        {"text": "Busca clientes en Upwork", "expected": ["marketing", "find_real_leads"]},
        {"text": "Hola", "expected": ["none"]},
    ]
    result = routing.run(llm, items)
    assert result["accuracy"] == 1.0
    assert "orchestrator_consult_calendar_agent" in llm.bound_names
    assert "rag_query_obsidian" in llm.bound_names


def test_dataset_labels_are_valid_tools():
    valid = {routing.label_for_tool(t.name) for t in routing.build_tool_specs()} | {"none"}
    items = datasets.load("routing")
    assert len(items) >= 40
    bad = [(i["text"], label) for i in items for label in i["expected"] if label not in valid]
    assert not bad
