"""Routing eval: which tool does the orchestrator LLM pick first for each request?

No sub-agent is executed. The LLM gets the real orchestrator prompt and tool schemas
(names + descriptions) via bind_tools(), and we read only its first tool call.
Dataset: evals/datasets/routing.jsonl -> {"text": ..., "expected": ["label", ...alternatives]}
Labels: sub-agent key (e.g. "taskforge"), a direct tool name, or "none" (answers directly).
"""

from __future__ import annotations

import logging
from typing import Callable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool, StructuredTool

from evals import metrics

log = logging.getLogger("ai_forge.evals")

PREFIX = "orchestrator_consult_"


def label_for_tool(tool_name: str) -> str:
    """orchestrator_consult_taskforge_agent -> taskforge; other tool names are kept as-is."""
    if tool_name.startswith(PREFIX):
        name = tool_name[len(PREFIX):]
        return name[: -len("_agent")] if name.endswith("_agent") else name
    return tool_name


def build_tool_specs() -> list[BaseTool]:
    """Same names/descriptions the orchestrator sees, with no-op bodies (never executed)."""
    from agents.orchestrator_tools import SUBAGENTS, find_real_leads, tool_name
    from agents.rag_tools import rag_index_obsidian_vault, rag_query_obsidian

    def _noop(task: str) -> str:
        return ""

    specs: list[BaseTool] = [
        StructuredTool.from_function(func=_noop, name=tool_name(agent), description=desc)
        for agent, _, desc in SUBAGENTS
    ]
    return specs + [find_real_leads, rag_query_obsidian, rag_index_obsidian_vault]


def predict(bound_llm, system_prompt: str, text: str) -> str:
    """First tool label, "none" for a direct answer, or "error" if the model call fails."""
    try:
        msg = bound_llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=text)])
    except Exception:  # one bad generation (e.g. Ollama repeat limit) must not abort the whole eval
        log.exception("Routing prediction failed for %r", text[:60])
        return "error"
    calls = getattr(msg, "tool_calls", None) or []
    return label_for_tool(calls[0]["name"]) if calls else "none"


def score(items: list[dict], preds: list[str]) -> dict:
    """An answer is correct if it is any of the accepted labels; the matrix uses the primary one."""
    gold_primary = [item["expected"][0] for item in items]
    # Count an accepted alternative as the primary label so it is not a confusion.
    normalized = [item["expected"][0] if p in item["expected"] else p for item, p in zip(items, preds)]
    errors = [
        {"text": item["text"], "expected": item["expected"], "predicted": p, "source": item.get("source")}
        for item, p in zip(items, preds)
        if p not in item["expected"]
    ]
    return {
        "n": len(items),
        "accuracy": round(metrics.accuracy(gold_primary, normalized), 3),
        "per_class": metrics.per_class_report(gold_primary, normalized),
        "confusion": metrics.confusion_matrix(gold_primary, normalized),
        "errors": errors,
    }


def run(llm, items: list[dict], progress: Callable[[int, int], None] | None = None) -> dict:
    from agents.orchestrator import ORCH_PROMPT

    bound = llm.bind_tools(build_tool_specs())
    preds = []
    for i, item in enumerate(items, start=1):
        preds.append(predict(bound, ORCH_PROMPT, item["text"]))
        if progress:
            progress(i, len(items))
    return score(items, preds)


def summary(result: dict) -> str:
    lines = [f"Routing accuracy: {result['accuracy']:.1%} ({result['n']} requests)", ""]
    lines.append(metrics.format_report(result["per_class"]))
    lines += ["", metrics.format_confusion(result["confusion"])]
    if result["errors"]:
        lines += ["", "Misrouted:"]
        lines += [f"  - {e['text'][:60]!r}: expected {e['expected'][0]}, got {e['predicted']}" for e in result["errors"]]
    return "\n".join(lines)
