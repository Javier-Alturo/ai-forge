"""RAG: a missing Chroma collection maps to the 'not indexed yet' path, not a crash."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

chromadb = pytest.importorskip("chromadb")
pytest.importorskip("llama_index.core")

from agents import rag_tools  # noqa: E402


def test_missing_collection_error_is_caught(tmp_path):
    client = chromadb.PersistentClient(path=str(tmp_path / "db"))
    with pytest.raises(rag_tools._COLLECTION_MISSING):
        client.get_collection("does_not_exist")
