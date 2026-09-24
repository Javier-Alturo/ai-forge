"""Tools LangChain del agente de memoria (ChromaDB + embeddings)."""

from __future__ import annotations

from langchain_core.tools import tool

from agents.a2a_log import a2a_log
from agents.chroma_memory import (
    delete_by_id,
    get_context_for_query,
    list_memory,
    semantic_search,
)
from agents.memory_manager import write as mem_write



@tool
def memory_list_all() -> str:
    """Lista todos los recordatorios, progreso y notas indexadas en ChromaDB."""
    a2a_log("memory", "chromadb", "list_all")
    return list_memory()


@tool
def memory_add_reminder(text: str) -> str:
    """Crea un recordatorio. text: contenido del recordatorio en lenguaje natural."""
    return mem_write(text, kind="reminder", priority=2)


@tool
def memory_add_progress(text: str) -> str:
    """Añade una nota de progreso o log. text: descripción del avance."""
    return mem_write(text, kind="progress", priority=1)



@tool
def memory_delete_reminder(item_id: str) -> str:
    """Elimina un recordatorio por su id corto (ej. ab12cd34)."""
    a2a_log("memory", "chromadb", "delete_reminder", item_id)
    return delete_by_id("reminder", item_id)


@tool
def memory_delete_progress(item_id: str) -> str:
    """Elimina una entrada de progreso por su id corto."""
    a2a_log("memory", "chromadb", "delete_progress", item_id)
    return delete_by_id("progress", item_id)


@tool
def memory_semantic_search(query: str, n_results: int = 8) -> str:
    """Busca recuerdos similares semánticamente a la consulta (embeddings locales)."""
    a2a_log("memory", "chromadb", "semantic_search", query[:200])
    return semantic_search(query, n_results=int(n_results))


@tool
def memory_add_embedding(text: str, kind: str = "note") -> str:
    """Guarda texto con embedding para búsqueda semántica. kind: etiqueta libre (p.ej. note, fact)."""
    return mem_write(text, kind=kind or "note", priority=1)



@tool
def memory_get_context(query: str, n: int = 6) -> str:
    """Recupera los N recuerdos más relevantes para un query (texto plano para contexto RAG interno)."""
    a2a_log("memory", "chromadb", "get_context", query[:200])
    return get_context_for_query(query, n=int(n)) or "(Sin contexto relevante.)"


def get_memory_tools():
    return [
        memory_list_all,
        memory_add_reminder,
        memory_add_progress,
        memory_delete_reminder,
        memory_delete_progress,
        memory_semantic_search,
        memory_add_embedding,
        memory_get_context,
    ]
