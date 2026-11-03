"""Tool calls written as plain text by the local model."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.orchestrator import make_repair_hook  # noqa: E402
from core.tool_call_repair import parse_text_tool_call, repair_message  # noqa: E402

FITNESS = "orchestrator_consult_fitness_agent"
CALENDAR = "orchestrator_consult_calendar_agent"
OBSIDIAN = "rag_query_obsidian"
NAMES = [FITNESS, CALENDAR, OBSIDIAN]


@pytest.mark.parametrize(("text", "name", "args"), [
    # Real outputs from qwen2.5:14b (request text replaced).
    (' sourceMapping_agent:consult_fitness_agent({"task": "x"})\n\n sourceMapping_agent ha devuelto X kilogramos.', FITNESS, {"task": "x"}),
    (' sourceMapping_agent_delegator:orchestrator_consult_calendar_agent {"task": "x"}', CALENDAR, {"task": "x"}),
    (' iNdEx\n{"name": "orchestrator_consult_fitness_agent", "arguments": {"task": "x"}}', FITNESS, {"task": "x"}),
    ('_icall_\n{"name": "rag_query_obsidian_agent", "arguments": {"question": "x"}}', OBSIDIAN, {"question": "x"}),
    (' علينй {"name": "orchestrator_consult_fitness_agent", "arguments": {"task": "x"}}', FITNESS, {"task": "x"}),
    ('{"name": "orchestrator_consult_fitness_agent", "arguments": {"task": "x"}}', FITNESS, {"task": "x"}),
])
def test_garbled_calls_are_parsed(text, name, args):
    call = parse_text_tool_call(text, NAMES)
    assert (call["name"], call["args"], call["type"]) == (name, args, "tool_call")
    assert call["id"]


@pytest.mark.parametrize("text", [
    "",
    "Tu última sesión de press banca fue el lunes.",
    # Sentences that mention a call must never fire a tool.
    'Puedes llamar a la herramienta así: {"name": "orchestrator_consult_fitness_agent", "arguments": {"task": "x"}}',
    'El agente consult_fitness_agent({"task": "x"}) sirve para eso.',
    # Unknown tools and malformed JSON.
    '{"name": "delete_everything", "arguments": {}}',
    ' iNdEx\n{"name": "orchestrator_consult_fitness_agent", "arguments": {"task"',
    '{"name": "orchestrator_consult_fitness_agent", "arguments": "x"}',
    'consult_fitness_agent({"task"',
])
def test_other_text_is_not_a_call(text):
    assert parse_text_tool_call(text, NAMES) is None


def test_repair_replaces_text_with_a_real_call():
    msg = AIMessage(content=' iNdEx\n{"name": "rag_query_obsidian", "arguments": {"question": "x"}}\nInventado', id="m1")
    fixed = repair_message(msg, NAMES)
    assert fixed.content == ""
    assert [c["name"] for c in fixed.tool_calls] == [OBSIDIAN]
    assert fixed.id == "m1"  # same id, so the graph replaces the message instead of adding one


def test_repair_leaves_normal_messages_alone():
    answer = AIMessage(content="Hola, ¿en qué te ayudo?")
    assert repair_message(answer, NAMES) is answer
    with_call = AIMessage(content=' sourceMapping', tool_calls=[{"name": FITNESS, "args": {}, "id": "1"}])
    assert repair_message(with_call, NAMES) is with_call
    blocks = AIMessage(content=[{"type": "text", "text": "hola"}])
    assert repair_message(blocks, NAMES) is blocks


class ScriptedChatModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def test_orchestrator_graph_runs_a_repaired_call():
    seen = []

    @tool
    def orchestrator_consult_fitness_agent(task: str) -> str:
        """Fitness agent."""
        seen.append(task)
        return "Press banca: 72.5 kg"

    model = ScriptedChatModel(responses=[
        AIMessage(content=' sourceMapping_agent:consult_fitness_agent({"task": "press banca"})\nLevantaste X kilogramos.', id="m1"),
        AIMessage(content="Levantaste 72.5 kg.", id="m2"),
    ])
    graph = create_react_agent(
        model, tools=[orchestrator_consult_fitness_agent],
        post_model_hook=make_repair_hook([FITNESS]),
    )
    final = graph.invoke({"messages": [HumanMessage(content="¿Cuánto levanté?")]})
    assert seen == ["press banca"]
    assert final["messages"][-1].content == "Levantaste 72.5 kg."
    assert not any("X kilogramos" in str(m.content) for m in final["messages"])
