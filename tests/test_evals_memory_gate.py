"""MemoryGate eval with a fake LLM (no Ollama needed)."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals import datasets  # noqa: E402
from evals.suites import memory_gate  # noqa: E402


class FakeLLM:
    """Answers the gate's JSON prompt from a fixed table keyed by a word in the fragment."""

    def __init__(self, table):
        self.table = table

    def invoke(self, messages):
        prompt = messages[-1].content
        fragment = prompt.split("FRAGMENTO:", 1)[1]
        mtype, conf = next(((t, c) for kw, t, c in self.table if kw in fragment), ("ephemeral", 0.0))
        content = json.dumps({"memory_type": mtype, "confidence": conf, "reason": "fake"})
        return type("Msg", (), {"content": "Claro:\n" + content})()


def test_score_counts_ephemeral_leaks():
    items = [
        {"text": "hola", "expected": "ephemeral"},
        {"text": "uso python", "expected": "fact"},
        {"text": "prefiero tablas", "expected": "preference"},
    ]
    preds = [("fact", True), ("fact", True), ("preference", False)]
    result = memory_gate.score(items, preds)
    assert result["ephemeral_leak_rate"] == 1.0
    assert result["store_recall"] == 0.5
    assert result["accuracy"] == round(2 / 3, 3)


def test_run_uses_real_gate_thresholds():
    llm = FakeLLM([("Python", "fact", 0.9), ("Prefiero", "preference", 0.5), ("Hola", "fact", 0.8)])
    items = [
        {"text": "Usuario: uso Python", "expected": "fact"},
        {"text": "Usuario: Prefiero tablas", "expected": "preference"},  # confidence 0.5 < 0.65 -> not stored
        {"text": "Usuario: Hola", "expected": "ephemeral"},  # misclassified as fact -> leak
    ]
    result = memory_gate.run(llm, items)
    assert result["store_recall"] == 0.5
    assert result["ephemeral_leak_rate"] == 1.0
    assert any("WOULD STORE" in line for line in memory_gate.summary(result).splitlines())


def test_dataset_is_balanced():
    items = datasets.load("memory_gate")
    counts = Counter(i["expected"] for i in items)
    assert set(counts) == set(memory_gate.LABELS)
    assert len(items) == 50 and set(counts.values()) == {10}
