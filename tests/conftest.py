"""Global pytest setup: tests never touch the user's real data.

Must run before agents.chroma_client / agents.rag_tools are imported, which is why it
lives in conftest.py (pytest loads it before collecting test modules).
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="aiforge_test_"))

# Fresh ChromaDB per test session instead of data/chromadb (semantic memory)
os.environ.setdefault("CHROMA_DIR", str(_TMP / "chromadb"))
# RAG documents go to a temp root instead of data/documents
os.environ.setdefault("_AI_FORGE_ROOT", str(_TMP))
# Use cached embedding models without contacting huggingface.co
os.environ.setdefault("HF_HUB_OFFLINE", "1")


def _ollama_up() -> bool:
    import urllib.request

    base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=2):
            return True
    except OSError:
        return False


def pytest_configure(config):
    config.addinivalue_line("markers", "requires_ollama: needs a running local Ollama (skipped otherwise, e.g. in CI)")


def pytest_collection_modifyitems(config, items):
    marked = [item for item in items if "requires_ollama" in item.keywords]
    if marked and not _ollama_up():
        import pytest

        skip = pytest.mark.skip(reason="Ollama not reachable (OLLAMA_BASE_URL); integration test skipped")
        for item in marked:
            item.add_marker(skip)
