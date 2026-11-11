"""Multi-part eval with a scripted fake LLM (no Ollama needed)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, ToolMessage

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals import datasets  # noqa: E402
from evals.suites import multi, routing  # noqa: E402

CODE = "orchestrator_consult_code_agent"
WEB = "orchestrator_consult_web_search_agent"
ITEM = {"text": "Factorial de 20 y qué es Zentrix", "parts": [
    {"tool": ["code"], "result": "El factorial es 2432902008176640000.", "expected": ["2432902008176640000"]},
    {"tool": ["web_search"], "result": "Zentrix es una base de datos.", "expected": ["base de datos"]},
]}


class ScriptedLLM:
    """Calls `tools` on the first turn, then answers with `answer(tool_outputs)`."""

    def __init__(self, tools, answer):
        self.tools, self.answer = tools, answer

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        outputs = [m.content for m in messages if isinstance(m, ToolMessage)]
        if self.tools and not outputs:
            calls = [{"name": name, "args": {"task": "x"}, "id": f"c{i}"} for i, name in enumerate(self.tools)]
            return AIMessage(content="", tool_calls=calls)
        return AIMessage(content=self.answer(outputs))


@pytest.mark.parametrize(("tools", "answer", "outcome"), [
    ([CODE, WEB], lambda out: " ".join(out), "complete"),
    ([CODE, WEB], lambda out: "Es 2,432,902,008,176,640,000 y Zentrix es una base de datos.", "complete"),
    ([CODE, WEB], lambda out: "Es 24,329,020,081,766,400,000 y Zentrix es una base de datos.", "distorted"),
    ([CODE, WEB], lambda out: "El factorial es 2432902008176640000. Zentrix es un juego.", "distorted"),
    ([CODE], lambda out: "El factorial es 2432902008176640000. Zentrix es una base de datos.", "missing_tool"),
    ([], lambda out: "Listo, ya lo hice.", "missing_tool"),
])
def test_outcomes(tools, answer, outcome):
    result = multi.run(ScriptedLLM(tools, answer), [ITEM])
    assert result["outcomes"][outcome] == 1


def test_each_part_gets_its_own_result():
    seen = []
    multi.run(ScriptedLLM([CODE, WEB, "orchestrator_consult_fitness_agent"], lambda out: seen.extend(out) or ""), [ITEM])
    assert seen == [ITEM["parts"][0]["result"], ITEM["parts"][1]["result"], multi.NO_RESULTS]


def test_part_rates():
    result = multi.run(ScriptedLLM([CODE], lambda out: "No pude calcularlo."), [ITEM])
    assert result["parts_called_rate"] == 0.5 and result["parts_intact_rate"] == 0.0


@pytest.mark.parametrize(("answer", "fact", "expected"), [
    ("son 31.536.000 segundos", "31536000", True),
    ("son 31 536 000 segundos", "31536000", True),
    ("son 315360000 segundos", "31536000", False),
    ("pesa 137.5 kg", "137.5", True),
    ("id MEM-4471", "mem-4471", True),
])
def test_has_fact(answer, fact, expected):
    assert multi.has_fact(answer, fact) is expected


def test_a_failed_generation_is_an_error_not_a_crash():
    class Broken(ScriptedLLM):
        def invoke(self, messages):
            raise RuntimeError("repeat limit")

    assert multi.run(Broken([], None), [ITEM])["outcomes"]["error"] == 1


def test_generic_dataset_is_valid():
    labels = {routing.label_for_tool(spec.name) for spec in routing.build_tool_specs()}
    items = datasets.load("multi")
    assert len(items) >= 10
    for item in items:
        assert len(item["parts"]) == 2
        for part in item["parts"]:
            assert set(part["tool"]) <= labels
            assert all(multi.has_fact(part["result"], fact) for fact in part["expected"])
