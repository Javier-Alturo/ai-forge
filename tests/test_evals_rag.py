"""RAG eval scoring and isolation (fake index/query, no Ollama or embeddings needed)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals import datasets  # noqa: E402
from evals.suites import rag  # noqa: E402


@pytest.mark.parametrize("answer", [
    "No se encontraron documentos lo suficientemente relevantes para responder a tu pregunta.",
    "No sé, el contexto no lo menciona.",
    "La información no se menciona en los documentos.",
    "The context does not provide that information.",
    "No tengo información sobre eso.",
])
def test_abstention_detected(answer):
    assert rag.is_abstention(answer)


@pytest.mark.parametrize("answer", ["Se fundó en 2015 en Manizales.", "El TTL es de 15 minutos."])
def test_real_answers_are_not_abstentions(answer):
    assert not rag.is_abstention(answer)


def test_contains_all_ignores_case_and_accents():
    assert rag.contains_all("Tuestan los MIÉRCOLES", ["miercoles"])
    assert rag.contains_all("martes y jueves", ["martes", "jueves"])
    assert not rag.contains_all("solo los martes", ["martes", "jueves"])


def test_score():
    items = [
        {"question": "a", "expected": ["2015"]},
        {"question": "b", "expected": ["12"]},
        {"question": "c", "answerable": False},
        {"question": "d", "answerable": False},
    ]
    result = rag.score(items, ["Fue en 2015", "No sé", "No sé", "El CEO es Ana"])
    assert result["answer_accuracy"] == 0.5
    assert result["abstention_rate"] == 0.5 and result["hallucination_rate"] == 0.5
    assert result["false_abstention_rate"] == 0.5
    assert len(result["errors"]) == 2
    assert [a["answer"] for a in result["answers"]][0] == "Fue en 2015"


def test_run_is_isolated_from_real_store():
    from agents import chroma_client, rag_tools

    before = (chroma_client.CHROMA_DIR, rag_tools.DOC_DIR)
    seen_dirs = []

    def fake_index(doc):
        seen_dirs.append(rag_tools.DOC_DIR)
        return "ok"

    items = [{"question": "¿En qué año se fundó Órbita Café?", "expected": ["2015"]}]
    result = rag.run(items, [datasets.GENERIC_DIR / "rag_docs"], index_fn=fake_index, query_fn=lambda q: "En 2015.")
    assert result["answer_accuracy"] == 1.0 and result["n_documents"] == 4
    assert seen_dirs and all("aiforge_rag_eval_" in str(d) for d in seen_dirs)
    assert (chroma_client.CHROMA_DIR, rag_tools.DOC_DIR) == before


def test_dataset_shape():
    items = datasets.load("rag")
    answerable = [i for i in items if i.get("answerable", True)]
    assert len(answerable) == 20 and len(items) - len(answerable) == 5
    assert all(i["expected"] for i in answerable)
