"""Grounding eval with a scripted fake LLM (no Ollama needed)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, ToolMessage

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals import datasets  # noqa: E402
from evals.suites import grounding, routing  # noqa: E402

FITNESS = "orchestrator_consult_fitness_agent"
CALENDAR = "orchestrator_consult_calendar_agent"
ITEM = {"text": "Mis récords de sentadilla", "tool": ["fitness"], "result": "Sentadilla 1RM 137.5 kg", "expected": ["137.5"]}


class ScriptedLLM:
    """Calls `tool` (if any) on the first turn, then answers with `answer(tool_output)`."""

    def __init__(self, tool, answer):
        self.tool, self.answer = tool, answer
        self.bound_names = []
        self.seen_tool_outputs = []

    def bind_tools(self, tools):
        self.bound_names = [t.name for t in tools]
        return self

    def invoke(self, messages):
        outputs = [m.content for m in messages if isinstance(m, ToolMessage)]
        if self.tool and not outputs:
            return AIMessage(content="", tool_calls=[{"name": self.tool, "args": {"task": "x"}, "id": "c1"}])
        self.seen_tool_outputs = outputs
        return AIMessage(content=self.answer(outputs[0] if outputs else ""))


@pytest.mark.parametrize(("tool", "answer", "outcome"), [
    (FITNESS, lambda out: f"Tu récord es: {out}", "grounded"),
    (FITNESS, lambda out: "Tu récord es 120 kg.", "ignored"),
    (CALENDAR, lambda out: "No encontré nada.", "wrong_tool"),
    (None, lambda out: "Tu récord es 140 kg.", "no_tool"),
])
def test_outcomes(tool, answer, outcome):
    result = grounding.run(ScriptedLLM(tool, answer), [ITEM])
    assert result["outcomes"][outcome] == 1


def test_only_expected_agent_returns_the_canned_result():
    llm = ScriptedLLM(CALENDAR, lambda out: out)
    grounding.run(llm, [ITEM])
    assert llm.seen_tool_outputs == [grounding.NO_RESULTS]
    assert FITNESS in llm.bound_names and "rag_query_obsidian" in llm.bound_names


def test_ignore_rate_counts_only_runs_that_reached_the_agent():
    items = [ITEM] * 4
    runs = [
        {"called": ["fitness"], "answer": "137.5 kg"},
        {"called": ["fitness"], "answer": "unos 120 kg"},
        {"called": [], "answer": "140 kg"},
        {"called": [], "answer": "", "outcome": "error"},
    ]
    result = grounding.score(items, runs)
    assert result["grounding_rate"] == 0.25
    assert result["ignore_rate"] == 0.5
    assert [f["outcome"] for f in result["failures"]] == ["ignored", "no_tool", "error"]


def test_loop_stops_after_max_steps():
    class Looping(ScriptedLLM):
        def invoke(self, messages):
            return AIMessage(content="", tool_calls=[{"name": FITNESS, "args": {"task": "x"}, "id": "c"}])

    result = grounding.run(Looping(None, None), [ITEM])
    assert result["outcomes"]["ignored"] == 1


def test_failed_call_counts_as_error_not_crash():
    class Broken(ScriptedLLM):
        def invoke(self, messages):
            raise RuntimeError("token repeat limit reached")

    result = grounding.run(Broken(None, None), [ITEM])
    assert result["outcomes"]["error"] == 1


def test_dataset_is_valid():
    valid = {routing.label_for_tool(t.name) for t in routing.build_tool_specs()}
    items = datasets.load("grounding")
    assert len(items) >= 15
    for item in items:
        assert set(item["tool"]) <= valid, item["text"]
        # Every expected fact must be in the canned result, or no answer could ever pass.
        assert grounding.rag.contains_all(item["result"], item["expected"]), item["text"]
