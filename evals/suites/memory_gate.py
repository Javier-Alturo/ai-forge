"""MemoryGate eval: does the gate classify each turn correctly and never store EPHEMERAL?

Calls MemoryGate._classify() (the production classifier) without touching ChromaDB.
Dataset: evals/datasets/memory_gate.jsonl -> {"text": ..., "expected": "fact|preference|decision|event|ephemeral"}
"""

from __future__ import annotations

from typing import Callable

from evals import metrics

LABELS = ("fact", "preference", "decision", "event", "ephemeral")


def classify(gate, text: str, context: str = "") -> tuple[str, bool]:
    """(predicted type, would it be stored?) using the real gate thresholds."""
    candidate = gate._classify(text, context)
    return candidate.memory_type.value, candidate.is_worth_storing


def score(items: list[dict], preds: list[tuple[str, bool]]) -> dict:
    gold = [item["expected"] for item in items]
    pred_labels = [label for label, _ in preds]
    stored = [s for _, s in preds]

    ephemeral_idx = [i for i, g in enumerate(gold) if g == "ephemeral"]
    keep_idx = [i for i, g in enumerate(gold) if g != "ephemeral"]
    leaks = [i for i in ephemeral_idx if stored[i]]
    errors = [
        {"text": item["text"], "expected": g, "predicted": p, "stored": s, "source": item.get("source")}
        for item, g, p, s in zip(items, gold, pred_labels, stored)
        if g != p or (g == "ephemeral" and s)
    ]
    return {
        "n": len(items),
        "accuracy": round(metrics.accuracy(gold, pred_labels), 3),
        "per_class": metrics.per_class_report(gold, pred_labels),
        "confusion": metrics.confusion_matrix(gold, pred_labels),
        # Safety: share of EPHEMERAL turns the gate would have written to memory (target: 0)
        "ephemeral_leak_rate": round(len(leaks) / len(ephemeral_idx), 3) if ephemeral_idx else 0.0,
        # Usefulness: share of turns worth remembering that would actually be stored
        "store_recall": round(sum(stored[i] for i in keep_idx) / len(keep_idx), 3) if keep_idx else 0.0,
        "errors": errors,
    }


def run(llm, items: list[dict], progress: Callable[[int, int], None] | None = None) -> dict:
    from agents.memory.memory_gate import MemoryGate

    gate = MemoryGate(llm, chroma_collection=None)  # _classify never touches the collection
    preds = []
    for i, item in enumerate(items, start=1):
        preds.append(classify(gate, item["text"], item.get("context", "")))
        if progress:
            progress(i, len(items))
    return score(items, preds)


def summary(result: dict) -> str:
    lines = [
        f"MemoryGate accuracy: {result['accuracy']:.1%} ({result['n']} turns)",
        f"EPHEMERAL leak rate: {result['ephemeral_leak_rate']:.1%}  (target 0%)",
        f"Store recall (non-ephemeral stored): {result['store_recall']:.1%}",
        "",
        metrics.format_report(result["per_class"]),
        "",
        metrics.format_confusion(result["confusion"]),
    ]
    if result["errors"]:
        lines += ["", "Errors:"]
        lines += [
            f"  - {e['text'][:60]!r}: expected {e['expected']}, got {e['predicted']}"
            + (" (WOULD STORE)" if e["expected"] == "ephemeral" and e["stored"] else "")
            for e in result["errors"]
        ]
    return "\n".join(lines)
