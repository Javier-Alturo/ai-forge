"""Singleton ChromaDB PersistentClient compartido por todos los modulos de AI-Forge.

Centralizar el cliente evita multiples instancias apuntando al mismo directorio
(chroma_memory, rag_tools, obsidian rag) que pueden causar conflictos de escritura.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
CHROMA_DIR = Path(os.environ.get("CHROMA_DIR", _ROOT / "data" / "chromadb"))

_client: Any = None


def get_chroma_client():
    """Devuelve el cliente ChromaDB singleton. Lo crea en el primer uso."""
    global _client
    if _client is None:
        import chromadb

        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client
