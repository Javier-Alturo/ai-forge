"""RAG eval: index fixed fictional documents into a temporary ChromaDB, ask questions.

- answerable questions: correct if every expected string is in the answer
  (lowercase, accents removed) -> "answer accuracy".
- unanswerable questions: correct if the system abstains ("no sé" / nothing found)
  -> "abstention rate"; the opposite is the hallucination rate.
Dataset: evals/datasets/rag.jsonl + documents in evals/datasets/rag_docs/.
The user's real ChromaDB and data/documents are never touched.
"""

from __future__ import annotations

import contextlib
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Callable, Iterator

ABSTENTION_PATTERNS = (
    r"no se encontraron", r"\bno (lo )?se\b", r"no tengo (esa |suficiente )?informacion", r"no hay informacion",
    r"no se menciona", r"no (se )?especifica", r"no (esta|aparece) (disponible|en)", r"no (puedo|es posible) responder",
    r"no (contiene|incluye|proporciona)", r"no se indica", r"sin informacion", r"desconozco",
    r"not (mentioned|provided|specified|available)", r"no information", r"i don'?t know", r"does not (provide|mention|contain)",
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def is_abstention(answer: str) -> bool:
    norm = normalize(answer)
    return any(re.search(p, norm) for p in ABSTENTION_PATTERNS)


def contains_all(answer: str, expected: list[str]) -> bool:
    norm = normalize(answer)
    return all(normalize(e) in norm for e in expected)


def score(items: list[dict], answers: list[str]) -> dict:
    answerable = [(i, a) for i, a in zip(items, answers) if i.get("answerable", True)]
    unanswerable = [(i, a) for i, a in zip(items, answers) if not i.get("answerable", True)]
    correct = [contains_all(a, i["expected"]) for i, a in answerable]
    abstained = [is_abstention(a) for _, a in unanswerable]
    errors = [
        {"question": i["question"], "expected": i["expected"], "answer": a[:300], "source": i.get("source")}
        for (i, a), ok in zip(answerable, correct) if not ok
    ] + [
        {"question": i["question"], "expected": "abstain", "answer": a[:300], "source": i.get("source")}
        for (i, a), ok in zip(unanswerable, abstained) if not ok
    ]
    n_ans, n_unans = len(answerable), len(unanswerable)
    return {
        "n_answerable": n_ans,
        "n_unanswerable": n_unans,
        "answer_accuracy": round(sum(correct) / n_ans, 3) if n_ans else 0.0,
        "abstention_rate": round(sum(abstained) / n_unans, 3) if n_unans else 0.0,
        "hallucination_rate": round(1 - sum(abstained) / n_unans, 3) if n_unans else 0.0,
        # answerable questions where the system said "I don't know" (retrieval or cutoff too strict)
        "false_abstention_rate": round(
            sum(is_abstention(a) for _, a in answerable) / n_ans, 3) if n_ans else 0.0,
        "errors": errors,
        # Every answer, so a run can be audited (or re-scored by an LLM judge) without re-running it
        "answers": [{"question": i["question"], "answer": a, "source": i.get("source")} for i, a in zip(items, answers)],
    }


@contextlib.contextmanager
def isolated_rag_store() -> Iterator[Path]:
    """Point agents.rag_tools at a fresh temp ChromaDB + documents dir, then restore."""
    from agents import chroma_client, rag_tools

    saved = (chroma_client.CHROMA_DIR, chroma_client._client, rag_tools.CHROMA_DIR, rag_tools.DOC_DIR)
    with tempfile.TemporaryDirectory(prefix="aiforge_rag_eval_", ignore_cleanup_errors=True) as tmp:
        tmp_path = Path(tmp)
        chroma_client.CHROMA_DIR = rag_tools.CHROMA_DIR = tmp_path / "chromadb"
        chroma_client._client = None
        rag_tools.DOC_DIR = tmp_path / "documents"
        try:
            yield tmp_path
        finally:
            chroma_client.CHROMA_DIR, chroma_client._client, rag_tools.CHROMA_DIR, rag_tools.DOC_DIR = saved


def _default_index(doc: Path) -> str:
    from agents.rag_tools import rag_add_document

    return rag_add_document.invoke({"filename": doc.name, "content": doc.read_text(encoding="utf-8")})


def _default_query(question: str) -> str:
    from agents.rag_tools import rag_query

    return rag_query.invoke({"question": question})


def run(
    items: list[dict],
    doc_dirs: list[Path],
    progress: Callable[[int, int], None] | None = None,
    index_fn: Callable[[Path], str] = _default_index,
    query_fn: Callable[[str], str] = _default_query,
) -> dict:
    docs = sorted(p for d in doc_dirs if d.exists() for p in d.iterdir() if p.suffix in {".md", ".txt"})
    with isolated_rag_store():
        for doc in docs:
            index_fn(doc)
        answers = []
        for i, item in enumerate(items, start=1):
            answers.append(query_fn(item["question"]))
            if progress:
                progress(i, len(items))
    result = score(items, answers)
    result["n_documents"] = len(docs)
    return result


def summary(result: dict) -> str:
    lines = [
        f"RAG over {result['n_documents']} documents",
        f"Answer accuracy (answerable, n={result['n_answerable']}): {result['answer_accuracy']:.1%}",
        f"Abstention on unanswerable (n={result['n_unanswerable']}): {result['abstention_rate']:.1%}"
        f"  -> hallucination rate {result['hallucination_rate']:.1%}",
        f"False 'no sé' on answerable: {result['false_abstention_rate']:.1%}",
    ]
    if result["errors"]:
        lines += ["", "Errors:"]
        lines += [f"  - {e['question'][:55]!r}: expected {e['expected']}, got {e['answer'][:80]!r}"
                  for e in result["errors"]]
    return "\n".join(lines)
