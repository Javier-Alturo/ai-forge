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
