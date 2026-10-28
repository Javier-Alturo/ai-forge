"""Grounding eval: when the orchestrator calls the right agent, does its answer use what came back?

Routing only scores the first tool call. Here the LLM runs the full tool loop (real orchestrator
prompt and tool schemas), but every tool returns canned text instead of running a sub-agent:
the expected one returns a fictional result with facts the model cannot guess, the rest return
"no results". The final answer is then checked for those facts.
Dataset: evals/datasets/grounding.jsonl -> {"text": ..., "tool": ["fitness"], "result": ..., "expected": ["137.5"]}
("tool" lists the agents that may answer; all of them return the canned result.)

Outcomes: grounded (right tool, facts in the answer), ignored (right tool, facts missing),
wrong_tool (only other tools), no_tool (answered directly), error.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Callable

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool

from evals.suites import rag, routing

log = logging.getLogger("ai_forge.evals")

OUTCOMES = ("grounded", "ignored", "wrong_tool", "no_tool", "error")
NO_RESULTS = "Sin resultados para esta consulta."
MAX_STEPS = 4


def build_canned_tools(expected: list[str], result: str) -> list[BaseTool]:
    """Same names/descriptions as the orchestrator's tools; only the expected ones return data."""
    tools = []
    for spec in routing.build_tool_specs():
        text = result if routing.label_for_tool(spec.name) in expected else NO_RESULTS
        tools.append(StructuredTool.from_function(
            func=lambda _text=text, **_: _text, name=spec.name, description=spec.description,
            args_schema=spec.args_schema,
        ))
    return tools


def run_item(llm, system_prompt: str, item: dict) -> dict:
    """Run the tool loop for one request; return the labels called and the final answer."""
    tools = {t.name: t for t in build_canned_tools(item["tool"], item["result"])}
    bound = llm.bind_tools(list(tools.values()))
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=item["text"])]
    called: list[str] = []
    for _ in range(MAX_STEPS):
        msg = bound.invoke(messages)
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


def classify(item: dict, called: list[str], answer: str) -> str:
    if any(label in item["tool"] for label in called):
        return "grounded" if rag.contains_all(answer, item["expected"]) else "ignored"
    return "wrong_tool" if called else "no_tool"


def score(items: list[dict], runs: list[dict]) -> dict:
    outcomes = [run.get("outcome") or classify(item, run["called"], run["answer"]) for item, run in zip(items, runs)]
    counts = Counter(outcomes)
    n = len(items)
    reached = counts["grounded"] + counts["ignored"]
    return {
        "n": n,
        "grounding_rate": round(counts["grounded"] / n, 3) if n else 0.0,
        # The question routing cannot answer: of the times the right agent was called, how often was its result dropped?
        "ignore_rate": round(counts["ignored"] / reached, 3) if reached else 0.0,
        "outcomes": {o: counts[o] for o in OUTCOMES},
        "failures": [
            {"text": item["text"], "tool": item["tool"], "outcome": o, "called": run["called"],
             "answer": run["answer"][:300], "source": item.get("source")}
            for item, run, o in zip(items, runs, outcomes)
            if o != "grounded"
        ],
    }


def run(llm, items: list[dict], progress: Callable[[int, int], None] | None = None) -> dict:
    from agents.orchestrator import ORCH_PROMPT

    runs = []
    for i, item in enumerate(items, start=1):
        try:
            runs.append(run_item(llm, ORCH_PROMPT, item))
        except Exception:  # one bad generation must not abort the whole eval
            log.exception("Grounding run failed for %r", item["text"][:60])
            runs.append({"called": [], "answer": "", "outcome": "error"})
        if progress:
            progress(i, len(items))
    return score(items, runs)


def summary(result: dict) -> str:
    o = result["outcomes"]
    lines = [
        f"Grounding: {result['grounding_rate']:.1%} ({result['n']} requests)",
        f"Ignored the agent's result: {result['ignore_rate']:.1%} of the times the right agent was called",
        "  " + "  ".join(f"{k}={o[k]}" for k in OUTCOMES),
    ]
    if result["failures"]:
        lines += ["", "Failures:"]
        lines += [f"  - [{f['outcome']}] {f['text'][:60]!r} (called: {', '.join(f['called']) or '-'})" for f in result["failures"]]
    return "\n".join(lines)
