"""Memoria persistente: ChromaDB + embeddings (compat API con parámetro path ignorado)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.chroma_memory import (
    add_progress as _add_progress,
    add_reminder as _add_reminder,
    delete_by_id as _delete_by_id,
    list_memory as _list_memory,
)

# Deprecado: antes apuntaba a memory_store.json; mantenemos el símbolo por compatibilidad.
DEFAULT_STORE = Path(__file__).resolve().parent.parent / "memory_store.json"


def list_memory(path: Path | None = None) -> str:
    del path
    return _list_memory()


def add_reminder(text: str, path: Path | None = None) -> str:
    del path
    return _add_reminder(text)


def add_progress(text: str, path: Path | None = None) -> str:
    del path
    return _add_progress(text)


def delete_by_id(kind: str, item_id: str, path: Path | None = None) -> str:
    del path
    return _delete_by_id(kind, item_id)
