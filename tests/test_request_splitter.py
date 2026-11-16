"""Requests with several independent tasks are split and answered one task per turn."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import orchestrator  # noqa: E402
from core.request_splitter import looks_like_a_list, parse_parts, split_request  # noqa: E402

TWO = "Calcula el factorial de 10 y busca en internet qué es Rust"


class Splitter:
    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    def invoke(self, messages, config=None):
        self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        return AIMessage(content=self.reply)


def test_two_tasks_are_split():
    llm = Splitter('["Calcula el factorial de 10", "Busca en internet qué es Rust"]')
    assert split_request(llm, TWO) == ["Calcula el factorial de 10", "Busca en internet qué es Rust"]


def test_a_plain_request_never_reaches_the_model():
    llm = Splitter('["a", "b"]')
    assert split_request(llm, "Calcula el factorial de 10") == ["Calcula el factorial de 10"]
    assert llm.calls == 0


@pytest.mark.parametrize("reply", [
    '["Calcula el factorial de 10 y busca en internet qué es Rust"]',  # the model says it is one task
    "no es una lista", '["a", 3]', '["a", ""]', "[]", '["a", "b", "c", "d", "e"]',
    RuntimeError("repeat limit"),
])
def test_anything_unusable_keeps_the_request_whole(reply):
    assert split_request(Splitter(reply), TWO) == [TWO]


def test_reply_with_text_around_the_list_is_parsed():
    assert parse_parts('Claro:\n```json\n["a", "b"]\n```', "x") == ["a", "b"]


def test_splitting_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("AIFORGE_SPLIT_REQUESTS", "0")
    llm = Splitter('["a", "b"]')
    assert split_request(llm, TWO) == [TWO] and llm.calls == 0


@pytest.mark.parametrize(("text", "expected"), [
    ("Calcula el factorial de 10", False), ("Hola", False),
    (TWO, True), ("Haz esto, y aquello", True), ("1) uno 2) dos", True), ("Además dime la hora", True),
])
def test_looks_like_a_list(text, expected):
    assert looks_like_a_list(text) is expected


class Graph:
    """Records each turn's request; answers "ok <request>"."""

    def __init__(self):
        self.turns = []

    def invoke(self, state, config=None):
        text = state["messages"][0].content
        self.turns.append(text)
        return {"messages": [AIMessage(content=f"ok {text}")]}

    async def astream(self, state, config=None, stream_mode=None):
        text = state["messages"][0].content
        self.turns.append(text)
        yield AIMessageChunk(content=f"ok {text}"), {}


@pytest.fixture
def graph(monkeypatch):
    g = Graph()
    monkeypatch.setattr(orchestrator, "get_orchestrator_graph", lambda: g)
    monkeypatch.setattr(orchestrator, "_start_background", lambda *_: None)
    monkeypatch.setattr(orchestrator, "_independent_tasks", lambda text: ["tarea uno", "tarea dos"] if " y " in text else [text])
    return g


def test_run_turn_answers_each_task_as_its_own_turn(graph):
    assert orchestrator.run_turn("uno y dos").content == "ok tarea uno\n\nok tarea dos"
    assert graph.turns == ["tarea uno", "tarea dos"]


def test_run_turn_with_one_task_is_unchanged(graph):
    assert orchestrator.run_turn("solo una").content == "ok solo una"
    assert graph.turns == ["solo una"]


def test_stream_answers_each_task_in_order(graph):
    async def collect():
        return [chunk async for chunk in orchestrator.arun_turn_stream("uno y dos")]

    assert "".join(asyncio.run(collect())) == "ok tarea uno\n\nok tarea dos"
    assert graph.turns == ["tarea uno", "tarea dos"]
