"""Multi-part eval: one request that needs two agents. Are both called, and are both results reported intact?

Routing and grounding use one tool per request. Here every request has two independent parts, each
with its own agent and canned result. Same loop as grounding: real orchestrator prompt and tool
schemas, canned tool outputs.
Dataset: evals/datasets/multi.jsonl ->
  {"text": ..., "parts": [{"tool": ["code"], "result": "...", "expected": ["..."]}, {...}]}

Outcomes per request: complete (every part's agent called and its facts in the answer),
missing_tool (some part's agent never called, so that part is skipped or invented),
distorted (all agents called, but some fact is missing or changed in the answer), error.
A part that is an action (save, create) has no expected facts: only its call is required, since a
confirmation does not need to repeat internal ids.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool

from core.tool_call_repair import repair_message
from evals.suites import rag, routing

log = logging.getLogger("ai_forge.evals")

OUTCOMES = ("complete", "missing_tool", "distorted", "error")
NO_RESULTS = "Sin resultados para esta consulta."
MAX_STEPS = 6
_GROUPING = re.compile(r"(?<=\d)[,.\s](?=\d{3}(?!\d))")


def has_fact(answer: str, fact: str) -> bool:
    """A long integer may be regrouped (1,000,000) but must keep exactly its digits."""
    if fact.isdigit() and len(fact) > 4:
        return fact in re.findall(r"\d+", _GROUPING.sub("", answer))
    return rag.contains_all(answer, [fact])


def build_canned_tools(parts: list[dict]) -> list[BaseTool]:
    """Same names/descriptions as the orchestrator's tools; each part's agents return that part's result."""
    tools = []
    for spec in routing.build_tool_specs():
        label = routing.label_for_tool(spec.name)
        text = next((p["result"] for p in parts if label in p["tool"]), NO_RESULTS)
        tools.append(StructuredTool.from_function(
            func=lambda _text=text, **_: _text, name=spec.name, description=spec.description,
            args_schema=spec.args_schema,
        ))
    return tools


def run_item(llm, system_prompt: str, item: dict) -> dict:
    tools = {t.name: t for t in build_canned_tools(item["parts"])}
    bound = llm.bind_tools(list(tools.values()))
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=item["text"])]
    called: list[str] = []
    for _ in range(MAX_STEPS):
        msg = bound.invoke(messages)
        if isinstance(msg, AIMessage):
            msg = repair_message(msg, tools)
        messages.append(msg)
        calls = getattr(msg, "tool_calls", None) or []
        if not calls:
            return {"called": called, "answer": str(msg.content)}
        for call in calls:
            called.append(routing.label_for_tool(call["name"]))
            tool = tools.get(call["name"])
            output = tool.invoke(call.get("args") or {}) if tool else f"Tool desconocida: {call['name']}"
            messages.append(ToolMessage(content=output, tool_call_id=call.get("id") or call["name"]))
    return {"called": called, "answer": ""}


def part_status(part: dict, called: list[str], answer: str) -> tuple[bool, bool]:
    """(agent was called, its facts are in the answer)."""
    reached = any(label in part["tool"] for label in called)
    return reached, all(has_fact(answer, fact) for fact in part["expected"])


def classify(item: dict, called: list[str], answer: str) -> str:
    statuses = [part_status(part, called, answer) for part in item["parts"]]
    if not all(reached for reached, _ in statuses):
        return "missing_tool"
    return "complete" if all(ok for _, ok in statuses) else "distorted"


def score(items: list[dict], runs: list[dict]) -> dict:
    outcomes = [run.get("outcome") or classify(item, run["called"], run["answer"]) for item, run in zip(items, runs)]
    counts = Counter(outcomes)
    parts = [part_status(p, run["called"], run["answer"]) for item, run in zip(items, runs) for p in item["parts"]]
    reached = [ok for was_reached, ok in parts if was_reached]
    n = len(items)
    return {
        "n": n,
        "complete_rate": round(counts["complete"] / n, 3) if n else 0.0,
        "parts_called_rate": round(len(reached) / len(parts), 3) if parts else 0.0,
        # Of the parts whose agent did run, how often did its facts reach the answer unchanged?
        "parts_intact_rate": round(sum(reached) / len(reached), 3) if reached else 0.0,
        "outcomes": {o: counts[o] for o in OUTCOMES},
        "failures": [
            {"text": item["text"], "outcome": o, "called": run["called"], "answer": run["answer"][:300],
             "source": item.get("source")}
            for item, run, o in zip(items, runs, outcomes)
            if o != "complete"
        ],
    }


def run(llm, items: list[dict], progress: Callable[[int, int], None] | None = None) -> dict:
    from agents.orchestrator import ORCH_PROMPT

    runs = []
    for i, item in enumerate(items, start=1):
        try:
            runs.append(run_item(llm, ORCH_PROMPT, item))
        except Exception:  # one bad generation must not abort the whole eval
            log.exception("Multi-part run failed for %r", item["text"][:60])
            runs.append({"called": [], "answer": "", "outcome": "error"})
        if progress:
            progress(i, len(items))
    return score(items, runs)


def summary(result: dict) -> str:
    o = result["outcomes"]
    lines = [
        f"Multi-part: {result['complete_rate']:.1%} complete ({result['n']} requests, 2 agents each)",
        f"Parts whose agent was called: {result['parts_called_rate']:.1%}",
        f"Called parts reported intact: {result['parts_intact_rate']:.1%}",
        "  " + "  ".join(f"{k}={o[k]}" for k in OUTCOMES),
    ]
    if result["failures"]:
        lines += ["", "Failures:"]
        lines += [f"  - [{f['outcome']}] {f['text'][:60]!r} (called: {', '.join(f['called']) or '-'})" for f in result["failures"]]
    return "\n".join(lines)
